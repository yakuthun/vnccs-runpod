# VNCCS RunPod Image

Bu depo, VNCCS iş akışı için bütün Python paketlerini ve custom node'ları **Pod açılmadan önce** Docker image içine kurar.

## Neden bu yapı?

Pod başlangıcında `pip install` ve `git clone` çalıştırılmaz. Böylece:

- Torch/CUDA çalışan Pod sırasında değişmez.
- VNCCS klasörlerinin kurulmadan kalması engellenir.
- Image build aşamasında CPU smoke test yapılır.
- Gerekli dört VNCCS node'u görünmüyorsa image GitHub'a gönderilmez.
- Pod başlangıcında GPU gerçekten hazır olana kadar beklenir.
- Her sürüm ayrı ve değiştirilemez bir tag ile kullanılır.

## İçerik

- ComfyUI
- ComfyUI Manager
- ComfyUI VNCCS
- ComfyUI VNCCS Utils
- ComfyUI GGUF
- Impact Pack
- Impact Subpack
- SeedVR2 Video Upscaler
- Easy-Sam3

Kaynak depolar Dockerfile içinde commit SHA ile sabitlenmiştir.

## GitHub'da image oluşturma

1. Bu dosyaları `vnccs-runpod` adlı GitHub deposuna koy.
2. GitHub deposunda **Actions** sekmesine gir.
3. **Build VNCCS RunPod Image** iş akışını aç.
4. **Run workflow** düğmesine bas.
5. Sürüm olarak `v1.0.0` bırak.
6. Build yeşil olana kadar bekle.

Build sırasında Dockerfile, ComfyUI'yi CPU modunda başlatır ve şu node'ları API üzerinden kontrol eder:

- `CharacterCreatorV2`
- `VNCCS_CharacterGenerator`
- `VNCCS_ControlCenter`
- `VNCCS_PoseStudio`

Bunlardan biri eksikse build kırmızı olur; bozuk image yayınlanmaz.

## GHCR paketini public yapma

İlk başarılı build sonrasında GitHub profilindeki **Packages** bölümüne gir:

1. `vnccs-runpod` paketini aç.
2. **Package settings** bölümüne gir.
3. **Change visibility** seçeneğinden **Public** yap.

Public image RunPod tarafından kullanıcı adı/parola olmadan çekilebilir.

## RunPod template ayarları

Hesap: `yakuthun`

```text
Name: VNCCS Docker v1
Container Image: ghcr.io/yakuthun/vnccs-runpod:v1.0.0
Container Disk: 120 GB
Volume Disk: 0 GB
Network Volume: Yok
HTTP Port Label: ComfyUI
HTTP Port: 8188
TCP Ports: Boş
Start Command: TAMAMEN BOŞ
Docker Command: TAMAMEN BOŞ
```

**Start Command girmeyin.** Image kendi `/opt/scripts/start.sh` dosyasıyla başlar.

## Pod açılışında beklenen log

```text
VNCCS RunPod image başlatılıyor
GPU: NVIDIA ...
Torch: 2.8.0 CUDA: 12.8
Kurulu kaynak sürümleri:
...
Starting server
```

GPU henüz container'a bağlanmadıysa script en fazla dört dakika bekler. `CUDA_VISIBLE_DEVICES` değerini değiştirmez.

## Dosya konumları

```text
Modeller: /workspace/models
Input:    /workspace/input
Output:   /workspace/output
Temp:     /workspace/temp
```

Network Volume kullanılmadığı için Pod terminate edilince bu dosyalar silinir. Önce çıktıları bilgisayara indir.

## Güncelleme kuralı

`v1.0.0` tag'ini yeniden kullanma. Dockerfile veya node sürümleri değiştiğinde:

```text
v1.0.1
v1.1.0
```

gibi yeni bir tag ile workflow çalıştır ve RunPod template'indeki image tag'ini değiştir.
