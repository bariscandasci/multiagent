# Sadece kişisel / özel ağ kurulumu

Komuta merkezi genel internete açılmaz. Süreç `127.0.0.1:8000` adresini dinler. `BIND_IP` bir Tailscale adresi ise o arayüz de açılır. `0.0.0.0` ve genel bir IP reddedilir. Caddy başlatılmaz; 80 ve 443 yayınlanmaz.

`data/` konteynerin dışındadır. Yeniden oluşturma hafıza, ajan ayarları, CRM ve finans defterini silmez.

## 1. Docker

Ubuntu üzerinde:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Oturumu kapatıp açın. `docker compose version` komutu sürümü göstermelidir.

## 2. Tailscale

Sunucuyu tailnet'e alın. Sağlayıcının güvenlik duvarında 8000 portunu genel internete açmayın.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4
```

## 3. Ortam

```bash
cp .env.example .env
```

Canlı kurulum kilidi: `ADMIN_USERNAME` ve `ADMIN_PASSWORD` ikisi birden dolu olmalıdır. Biri boşsa kimlik doğrulama kapalı kalır. Bu haliyle servisi başlatmayın.

Ayrıca doldurun:

- `LLM_PROVIDER=gemini`
- `GEMINI_API_KEY` veya virgüllü `GEMINI_API_KEYS`
- `GEMINI_FALLBACK_MODEL`
- `LLM_RPM` ve `LLM_FALLBACK_RPM`
- `BIND_IP` — yalnız bu makine için `127.0.0.1`. Telefonda veya başka bilgisayarda açacaksanız `tailscale ip -4` çıktısı.

`data/` ve `backups/` uid 1000 ile yazılabilir olmalıdır:

```bash
mkdir -p data backups
sudo chown -R 1000:1000 data backups
```

## 4. Başlatma

```bash
docker compose up -d --build
docker compose ps
```

Sunucunun kendisinden:

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/robots.txt
```

Sağlık gövdesinde `status` değeri `ok`, `version` değeri `1.0.0` olur. Bu iki uç parola istemez. Arayüz ve diğer API uçları `ADMIN_USERNAME` / `ADMIN_PASSWORD` ister.

Tailscale istemcisinden adres `http://<BIND_IP>:8000` olur. Sunucunun genel IP'sinde 8000 dinleyicisi yoktur.

## 5. Loglar

```bash
docker compose logs -f app
docker compose logs -f backup
```

## 6. Yedek ve geri dönüş

`backup` servisi açılışta ve sonra her 24 saatte bir `backups/bcd-data-YYYYMMDDTHHMMSSZ.tar.gz` yazar. 14 günden eski arşivleri siler.

```bash
docker compose stop app
tar -tzf backups/bcd-data-YYYYMMDDTHHMMSSZ.tar.gz
tar -xzf backups/bcd-data-YYYYMMDDTHHMMSSZ.tar.gz
docker compose start app
```

Arşiv `data/` köküyle açılır. Komut proje dizininde çalıştırılmalıdır. `YYYYMMDDTHHMMSSZ` yerine dosya adındaki damgayı yazın.

## Notlar

Uvicorn tek süreçtir. Hız sınırı ve JSON kilitleri bu süreçte durur. `./data:/app/data` bağlantısı `hafiza.json`, `ajan_ayarlari.json`, `crm.json`, `finans/giderler.json` ve `projeler/` kayıtlarını taşır. Her yanıt `X-Robots-Tag: noindex, nofollow` taşır.
