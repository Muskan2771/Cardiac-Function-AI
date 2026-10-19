# Deployment guide

The whole product (API + web UI) is one Docker image that listens on `$PORT` (default 7860).
The recommended free host is a **Hugging Face Space (Docker SDK, CPU basic: 2 vCPU / 16 GB RAM)**.
Avoid hosts whose free tier has 512 MB of RAM (for example Render's free plan): PyTorch plus
DeepLabV3-ResNet50 needs roughly 1-1.5 GB.

## 0. Before you deploy: the model file

The trained weights (`deeplabv3_lv_segmentation.pth`, 168 MB) are **not in git** - GitHub
rejects files above 100 MB. Pick one way to get them into the container:

**Option A - Hugging Face model repo (recommended)**

1. Create a model repo at <https://huggingface.co/new> (public is simplest).
2. Upload `deeplabv3_lv_segmentation.pth` to it (web UI "Add file", or `huggingface-cli upload`).
3. In your Space: *Settings -> Variables and secrets*, add
   - variable `MODEL_URL` = `https://huggingface.co/<user>/<model-repo>/resolve/main/deeplabv3_lv_segmentation.pth`
   - variable `MODEL_SHA256` = output of `sha256sum deeplabv3_lv_segmentation.pth` (integrity check)
   - secret `MODEL_AUTH_TOKEN` = a read token, only if the model repo is private

On start-up the server downloads the file once and refuses to load it if the checksum differs.

**Option B - bake it into the image:** copy the `.pth` into `segmentation/checkpoints/`, remove
the `*.pth` line from `.gitignore` and use Git LFS. Not recommended; Option A keeps the repo small.

If the file is missing the app still starts; the page shows "model not loaded" and `/analyze`
answers `503`.

## 1. Create the Space

1. <https://huggingface.co/new-space> -> name it, **SDK: Docker -> Blank**, hardware **CPU basic**.
2. Push the code (from a clone of your GitHub repo):

   ```bash
   deploy/push_to_space.sh https://huggingface.co/spaces/<user>/<space-name>
   ```

   Git asks for your username and a **write** access token (Settings -> Access Tokens).
3. Open the Space's **Logs** tab. The first build takes about 5-10 minutes (installing PyTorch).
4. Your public URL is `https://<user>-<space-name>.hf.space`.

## 2. Verify the live service

```bash
BASE=https://<user>-<space-name>.hf.space
curl -s $BASE/health                       # model_loaded should be true
curl -s -F "file=@some_echo.avi" $BASE/analyze | python -m json.tool
```

Then open `$BASE` in a browser, upload a clip and check that the outline plays, EF and the
risk flag show, and the "screening aid, not a diagnosis" text is visible.

## Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `SEG_CKPT` | `segmentation/checkpoints/deeplabv3_lv_segmentation.pth` | checkpoint path |
| `MODEL_URL` / `MODEL_SHA256` / `MODEL_AUTH_TOKEN` | unset | download the checkpoint at start-up |
| `MAX_UPLOAD_MB` | 50 | reject larger uploads (HTTP 413) |
| `MIN_FRAMES` / `MAX_FRAMES` | 10 / 600 | accepted clip length (HTTP 422 otherwise) |
| `MAX_CONCURRENT` | 1 | simultaneous analyses (extra requests queue) |
| `OVERLAY_TTL_SECONDS` | 1800 | how long overlay frames are kept before deletion |
| `ALLOWED_ORIGINS` | local Vite dev server | CORS origins; not needed when UI and API share one URL |
| `PORT` | 7860 | listening port |

## Privacy

Uploaded videos are written to a temporary folder, deleted when the request finishes, and
only the rendered overlay JPEGs are kept (under an unguessable id) for 30 minutes. **Do not
upload real patient data to a public demo.** Use EchoNet-Dynamic clips or other de-identified
research data only.

## Run it yourself with Docker

```bash
docker build -t cardiac-function-ai .
docker run --rm -p 7860:7860 \
  -v "$PWD/segmentation/checkpoints:/home/appuser/app/segmentation/checkpoints:ro" \
  cardiac-function-ai
# open http://localhost:7860
```
