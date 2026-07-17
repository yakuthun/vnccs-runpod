# VNCCS RunPod v1.1.1 Kurtarma Paketi

Bu klasör, çalışan RunPod yapısının kaybolmaması için 17 Temmuz 2026
tarihinde oluşturulmuş bağımsız kaynak snapshot'ıdır. Büyük model dosyaları
Git'e veya Docker image'a gömülmez; sabit revision ve SHA-256 değerleriyle Pod
açıldıktan sonra indirilir.

## İçerik

- Pinlenmiş RunPod tabanını ve custom node kurulumunu içeren `Dockerfile`
- GitHub Actions image build tanımı
- Bize ait `VNCCS_SourcePoseSprite` Python ve JavaScript node paketi
- Adaptive ve No3D sprite workflow'ları
- Build, smoke-test, runtime, doğrulama ve model indirme scriptleri
- v19, v23 ve Pose Studio LoRA için tek komutluk doğrulamalı indirme scripti

Upstream VNCCS ve diğer custom node depoları Dockerfile içinde exact commit
SHA ile sabitlenmiştir. `vendor_ComfyUI_VNCCS` klasörüne ihtiyaç yoktur.

## Yeniden image oluşturma

Bu klasörün içeriğini yeni ve boş bir GitHub reposunun köküne koyup `Build
VNCCS RunPod Image` action'ını `v1.1.1` değeriyle çalıştırın. Hedef image:

```text
ghcr.io/yakuthun/vnccs-runpod:v1.1.1
```

RunPod template ayarları:

```text
Container Image: ghcr.io/yakuthun/vnccs-runpod:v1.1.1
Container Disk: 120 GB veya daha fazla
Volume Disk: 0 GB
HTTP Port: 8188
Start Command: boş
Docker Command: boş
```

## Her yeni Pod'da yapılacak işlem

Yalnızca v19, v23 ve Pose Studio LoRA gerekiyorsa terminalde:

```bash
/opt/vnccs/pod-download-core-models.sh
```

Sprite workflow'unun BiRefNet, SAM3D ve SAM3 dahil bütün modellerini kurmak
için bunun yerine:

```bash
/workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python \
  /opt/vnccs/download-workflow-models.py
```

İndirme bittikten sonra ComfyUI bir kez yeniden başlatılır. Ardından:

```bash
/workspace/runpod-slim/ComfyUI/.venv-cu128/bin/python \
  /opt/vnccs/verify-running-pod.py
```

Son satır `RUNPOD READY` olmalıdır.

## Bilinen kritik düzeltmeler

- Runtime, RunPod'un orijinal `/start.sh` dosyasını kullanır.
- `--disable-cuda-malloc` otomatik eklenir; BiRefNet yüklenirken görülen sahte
  CUDA OOM problemi bu şekilde önlenir.
- Runtime sırasında `pip install`, `git clone` veya custom node update yapılmaz.
- `CharacterCloner` içindeki Character Name boş bırakılamaz; örneğin `Niko`.
- Pose generation için
  `VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors` zorunludur.

## Snapshot kimliği

```text
Snapshot adı: v1.1.1
Kaynak repo: https://github.com/yakuthun/vnccs-runpod
Kaynak durum alınırken HEAD: b2e6831
Base image digest: sha256:d624068cb75df9bc7ea3304186bab792a8c2be02496d55e5fa59086c247d9694
```
