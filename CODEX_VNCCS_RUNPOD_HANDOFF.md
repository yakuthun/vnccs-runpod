# Codex Görevi: RunPod için güvenilir VNCCS–ComfyUI Docker image ve template

## Rolün

Bu işi baştan sona sahiplen. Yalnızca tavsiye verme; GitHub reposunu incele, gerekli dosyaları düzelt, commit et, GitHub Actions build’ini çalıştır, hata çıkarsa loglardan gerçek nedeni bulup düzelt ve image başarıyla yayınlanana kadar ilerle.

Tahminle peş peşe RunPod Pod açtırma. Ücretli GPU denemesi, ancak Docker build başarıyla tamamlandıktan ve build-time smoke test geçtiikten sonra yapılmalı.

## Repo

- GitHub: https://github.com/yakuthun/vnccs-runpod
- Hedef GHCR image:
  - `ghcr.io/yakuthun/vnccs-runpod:v1.0.0`
- Repo şu anda public.
- Önce mevcut dosyaları denetle. Özellikle `Dockerfile`, `.github/workflows/build-image.yml`, `scripts/` ve `README.md`.
- Mevcut repoda yanlışlıkla eski V1 tasarımı bulunabilir. Eski tasarımı körlemesine devam ettirme.

## Kullanıcının gerçek hedefi

RunPod Community Cloud üzerinde, çoğunlukla RTX 4090 veya en az 24 GB VRAM’li GPU ile VNCCS tabanlı bir ComfyUI workflow’u çalıştırmak.

Kullanım modeli:

1. Template ile yeni Pod açılır.
2. ComfyUI kısa sürede hazır olur.
3. Kullanıcı gerekli modelleri o Pod’da indirir.
4. Görselleri üretir.
5. Çıktıları bilgisayarına indirir.
6. Pod’u `Terminate` eder.
7. Durdurulmuş disk veya Network Volume ücreti kalmaz.

Kullanıcı Network Volume istemiyor. Her yeni Pod’da model dosyalarının yeniden indirilmesini kabul ediyor. Buna karşılık Python paketleri ve custom node’lar her Pod açılışında yeniden kurulmayacak; Docker image içinde hazır gelecek.

## RunPod template hedefi

```text
Name: VNCCS Docker v1
Container Image: ghcr.io/yakuthun/vnccs-runpod:v1.0.0
Container Disk: 120 GB
Volume Disk: 0 GB
Network Volume: none

HTTP Port:
  Label: ComfyUI
  Port: 8188

TCP Ports: empty
Start Command: completely empty
Docker Command: completely empty
```

Image kendi CMD/entrypoint’i ile başlamalı. Eski uzun shell Start Command yaklaşımına geri dönme.

## Bilinen çalışan taban

Temel image olarak bunu kullan:

```dockerfile
FROM runpod/comfyui:cuda12.8
```

Bu image önceki Pod’da ComfyUI ve CUDA ile açıldı. Başka bir `runpod/pytorch:*` tabanına sebepsiz geçme.

Bu tabandaki bilinen yollar:

```text
ComfyUI:
  /workspace/runpod-slim/ComfyUI

Python:
  /workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python
```

Docker build sırasında bu yolların gerçekten varlığını `test -f` ve `test -x` ile doğrula. Yoksa anlaşılır hata ile build’i durdur; sessiz fallback ile farklı Python kullanma.

## Gerekli custom node’lar

Image içine build sırasında kurulmalı:

```text
AHEKOT/ComfyUI_VNCCS
AHEKOT/ComfyUI_VNCCS_Utils
city96/ComfyUI-GGUF
ltdrdata/ComfyUI-Impact-Pack
ltdrdata/ComfyUI-Impact-Subpack
numz/ComfyUI-SeedVR2_VideoUpscaler
yolain/ComfyUI-Easy-Sam3
ComfyUI Manager
```

İlk stabil sürüm için kaynakları exact commit SHA ile sabitle:

```text
VNCCS:
050cb4b15875a7eefc180d1f00b97bf5e8b17104

VNCCS Utils:
1908ddfa8a5084a360783ca596f27678743c5496

ComfyUI-GGUF:
6ea2651e7df66d7585f6ffee804b20e92fb38b8a

Impact Pack:
429d0159ad429e64d2b3916e6e7be9c22d025c3c

Impact Subpack:
50c7b71a6a224734cc9b21963c6d1926816a97f1

SeedVR2:
4490bd1f482e026674543386bb2a4d176da245b9

Easy-Sam3:
88fe578a1a5e03d95281197303d5d3a73fd5a089

SAM2:
2b90b9f5ceec907a1c18123530e92e794ad901a4
```

ComfyUI core’u ayrıca clone edip base image içindeki sürümle karıştırma. Base image’ın kendi ComfyUI kurulumunu kullan.

## Önceki başarısızlıklar ve çıkarılan dersler

### 1. VNCCS klasörleri hiç kurulmadı

Bir template açılışında yalnızca `ComfyUI-Manager` vardı. Şunlar yoktu:

```text
custom_nodes/ComfyUI_VNCCS
custom_nodes/ComfyUI_VNCCS_Utils
```

Bu nedenle workflow şu node’ları eksik gösterdi:

```text
CharacterCreatorV2
VNCCS_CharacterGenerator
VNCCS_ControlCenter
VNCCS_PoseStudio
```

Manuel olarak iki VNCCS reposunu clone edip requirements kurulduğunda bu problem düzeldi.

### 2. Runtime pip işlemleri CUDA ortamını bozdu

Pod açılışında uzun `pip install` komutları çalıştırılan bir denemeden sonra ComfyUI şu hatayla çöktü:

```text
RuntimeError: CUDA unknown error
Setting the available devices to be zero
```

Dolayısıyla:

- Pod runtime’ında `pip install` yapma.
- Pod runtime’ında `git clone` yapma.
- Base image’ın Torch/CUDA paketlerini değiştirme.
- `torch`, `torchvision`, `torchaudio` ve `triton` custom-node requirements üzerinden yeniden kurulmasın.
- Bağımlılık kurulumu yalnızca Docker build sırasında yapılsın.
- Build sonrasında Torch sürümünü ve `torch.version.cuda` değerini kaydet ve doğrula.

### 3. GPU hemen hazır olmayabiliyor

Runtime başlangıç script’i:

- `CUDA_VISIBLE_DEVICES` değerini değiştirmemeli.
- `NVIDIA_VISIBLE_DEVICES` değerini değiştirmemeli.
- `nvidia-smi` ve aynı ComfyUI Python’ıyla `torch.cuda.is_available()` kontrolü yapmalı.
- Her denemeyi yeni Python process’i ile yapmalı; erken CUDA hatasının process içinde cache’lenmesine izin vermemeli.
- Yaklaşık dört dakika bekleyebilmeli.
- GPU hazır olunca ComfyUI’yi `exec` ile başlatmalı.
- GPU hazır olmazsa anlaşılır log ve ayrı exit code üretmeli.

### 4. Genel Manager popup’ı gerçek nedeni gizledi

ComfyUI’nin “önce comfyui-manager kurun” popup’ı Manager eksik olmasa bile node import edilemediğinde çıkabiliyor. Başarı kriteri popup değil, `/object_info` API’sindeki gerçek node kayıtları olmalı.

## Python bağımlılık politikası

Custom-node requirements dosyalarını doğrudan körlemesine kurma.

Bir helper script ile requirement satırlarını parse et ve en az şu paketlerin yeniden kurulmasını engelle:

```text
torch
torchvision
torchaudio
triton
```

`llama-cpp-python` için özel karar ver:

- VNCCS requirements içinde bulunuyor.
- Önceki manuel düzeltmede Torch/CUDA’yı korumak için filtrelendi ve dört node register oldu.
- Ancak bazı Qwen VL işlevleri runtime’da buna ihtiyaç duyabilir.
- Rastgele source build başlatma.
- Mevcut Python 3.12 / CUDA 12.8 ortamı için güvenilir, pinlenmiş ve mümkünse prebuilt wheel yolunu araştır.
- Kurulması gerekiyorsa Torch/CUDA’yı değiştirmediğini build sırasında doğrula.
- İlk image’da bilerek dışarıda bırakılıyorsa README’de hangi VNCCS işlevinin etkilenebileceğini açıkça yaz.
- Kullanıcının asıl workflow’u için gerekliyse işi “node register oluyor” seviyesinde bırakma; gerçek kullanım yolu için de çöz.

Impact Pack requirements içindeki hareketli SAM2 Git URL’sini doğrudan main’den kurma; yukarıdaki pinlenmiş SAM2 SHA’sını kullan.

Manager’ı base image’ın desteklediği yöntemle kur. `--enable-manager` ile başlat. Manager kurulumu base Torch/CUDA paketlerini upgrade etmemeli.

## Build-time doğrulama

Docker build’in sonlarında CPU smoke test çalıştır:

```text
ComfyUI Python:
  /workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python

main.py:
  /workspace/runpod-slim/ComfyUI/main.py

args:
  --cpu
  --listen 127.0.0.1
  --port 8199
  --enable-manager
  --disable-auto-launch
```

ComfyUI açılınca:

```text
GET http://127.0.0.1:8199/object_info
```

İçinde şu dört node’u zorunlu kontrol et:

```text
CharacterCreatorV2
VNCCS_CharacterGenerator
VNCCS_ControlCenter
VNCCS_PoseStudio
```

Bir tanesi bile yoksa:

- build başarısız olsun,
- tam ComfyUI logu yazılsın,
- image GHCR’a push edilmesin.

Ayrıca import failure loglarını görünür yap:

```text
ModuleNotFoundError
ImportError
CRITICAL REGISTRATION ERROR
IMPORT FAILED
```

Smoke test yalnızca port açıldı diye başarılı sayılmamalı.

## Runtime başlangıcı

Tek bir startup script kullan.

Beklenen davranış:

1. Build info’yu yazdır.
2. GPU’yu bekle.
3. Doğru Python ile CUDA kontrolü yap.
4. ComfyUI’yi tek process olarak başlat:

```bash
exec "$COMFYUI_PYTHON" "$COMFYUI_DIR/main.py" \
  --listen 0.0.0.0 \
  --port 8188 \
  --enable-manager \
  --disable-auto-launch
```

Base image’ın `/start.sh` dosyasını paralel şekilde körlemesine çalıştırma. Önce ne yaptığını incele. Eğer o da ComfyUI başlatıyorsa ikinci server ve port çakışması yaratma. Web Terminal/Jupyter korunacaksa bunu duplicate ComfyUI process’i yaratmadan çöz.

Runtime’da kesinlikle şunlar olmamalı:

```text
pip install
git clone
git pull
apt install
ComfyUI update
custom node update
```

## GitHub Actions

Workflow manuel çalıştırılabilsin:

```yaml
workflow_dispatch:
  inputs:
    version:
      default: v1.0.0
```

Gereken izinler:

```yaml
permissions:
  contents: read
  packages: write
```

Hedef image tag’leri:

```text
ghcr.io/yakuthun/vnccs-runpod:v1.0.0
ghcr.io/yakuthun/vnccs-runpod:sha-<shortsha>
```

`latest` tag’ini ilk stabilizasyon sırasında kullanma.

Build yalnızca `linux/amd64` için yeterli.

GitHub runner disk alanını kontrol et. Büyük base image nedeniyle disk tükenirse bunu logdan teşhis et ve güvenli cleanup uygula. Başarılı image build edilmeden RunPod denemesi isteme.

## GHCR

İlk başarılı build’den sonra package visibility ayrı olarak kontrol edilmeli. Repo public olsa bile GHCR package’ın public olduğundan emin ol.

RunPod’un image’ı credentials olmadan çekebilmesi için:

```text
ghcr.io/yakuthun/vnccs-runpod:v1.0.0
```

public pull ile erişilebilir olmalı.

## Modeller ve veri

Büyük model dosyalarını Docker image içine gömme.

Kullanıcı her yeni Pod’da modelleri indirmeyi kabul ediyor.

Network Volume yok. Pod terminate edilince veriler silinecek.

Kullanıcı iş bitmeden önce `/workspace/output` çıktısını bilgisayarına indirecek.

Model/input/output yollarını base image’ın gerçek düzeniyle uyumlu tut. Gereksiz symlink ile base image davranışını bozma. Yol değişikliği yapacaksan build ve runtime test ile doğrula.

## Güvenlik ve gizlilik

Repo şu anda public; Dockerfile veya workflow içine:

- token,
- RunPod API key,
- GitHub PAT,
- Hugging Face token,
- özel model URL’si,
- kişisel veri

yazma.

Secrets gerekiyorsa GitHub Actions secrets veya RunPod environment secrets kullan.

## Çalışma yöntemi

Şu sırayla ilerle:

1. Repo’yu audit et ve mevcut V1/V2 karışıklığını raporla.
2. Base image, paths, entrypoint/CMD ve mevcut Python ortamını Docker build bağlamında doğrula.
3. Minimal, pinlenmiş Dockerfile ve helper scriptleri düzelt.
4. Shell, Python ve YAML syntax kontrollerini çalıştır.
5. Branch oluştur ve anlamlı commitler yap.
6. GitHub Actions workflow’u çalıştır.
7. Build kırılırsa gerçek log satırını bul; tahminle paket listesi değiştirme.
8. Build-time `/object_info` smoke test yeşil olmadan image push’u başarılı kabul etme.
9. GHCR package’ın public pull durumunu doğrula.
10. Sonunda RunPod template için kullanıcıya yalnızca kesin alan değerlerini ver.
11. İlk gerçek Pod testinde:
    - image çekiliyor mu,
    - GPU bekleme doğru mu,
    - ComfyUI 8188 açılıyor mu,
    - dört VNCCS node’u mevcut mu,
    - workflow eksik node popup’ı vermeden yükleniyor mu
    doğrula.
12. İlk test başarısızsa kullanıcıya tekrar tekrar yeni Pod açtırmadan önce logdan kök nedeni çöz.

## Tamamlanma kriterleri

İş ancak aşağıdakilerin tamamı sağlanınca bitmiş sayılır:

- [ ] Repo’da doğru base image kullanılıyor: `runpod/comfyui:cuda12.8`
- [ ] ComfyUI core ayrıca clone edilip base image ile karıştırılmıyor.
- [ ] Custom node’lar exact commit SHA ile image içine kuruluyor.
- [ ] Runtime’da hiçbir paket/repo kurulumu yapılmıyor.
- [ ] Base Torch/CUDA stack korunuyor.
- [ ] Build-time ComfyUI smoke test başarılı.
- [ ] Dört VNCCS node’u `/object_info` içinde mevcut.
- [ ] GitHub Actions build yeşil.
- [ ] `ghcr.io/yakuthun/vnccs-runpod:v1.0.0` push edilmiş.
- [ ] GHCR package public pull edilebilir.
- [ ] Runtime startup GPU hazır olana kadar güvenli bekliyor.
- [ ] ComfyUI `0.0.0.0:8188` üzerinde açılıyor.
- [ ] RunPod template’te Start Command ve Docker Command boş.
- [ ] Fresh Pod’da workflow eksik node hatası vermiyor.
- [ ] Kullanıcı Pod’u iş bitince terminate ettiğinde kalıcı storage ücreti kalmıyor.

## İletişim biçimi

Kullanıcı teknik olabilir ama artık deneme-yanılma yüzünden çok yoruldu.

Bu nedenle:

- Aynı anda tek net adım ver.
- “Muhtemelen” diye rastgele komut yazma.
- Her değişiklikte hangi gerçek log/fact nedeniyle yaptığını söyle.
- RunPod üzerinde ücretli test istemeden önce build’in neden hazır olduğunu kanıtla.
- Hata olduğunda önce logu incele; Pod’u hemen terminate/deploy döngüsüne sokma.
- Çalışmadığı halde “hazır” veya “garanti” deme.
