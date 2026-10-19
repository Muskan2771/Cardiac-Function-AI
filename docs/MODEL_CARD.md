# Model card - LV segmentation (DeepLabV3-ResNet50)

| | |
|---|---|
| Task | Binary segmentation of the left ventricle in apical four-chamber echocardiogram frames |
| Architecture | torchvision `deeplabv3_resnet50`, classifier and auxiliary heads replaced by a 1-channel conv |
| Input | RGB frames resized to 112x112, ImageNet mean/std normalisation |
| Output | Per-frame mask, `uint8`, values {0, 1} (threshold 0.5 on the sigmoid) |
| Loss / optimiser | 0.5 BCE + 0.5 soft Dice, Adam (lr 1e-4), ReduceLROnPlateau |
| Augmentation | rotation +/-10 deg, brightness/contrast jitter; **no horizontal flip** |
| Intended use | Research / education demo; screening aid, **not a medical device** |

## Current weights: trained on synthetic data

The published checkpoint was trained for 6 epochs on 64 videos of a **synthetic
EchoNet-schema dataset** (`segmentation/make_synthetic_dataset.py`), because access to the real
EchoNet-Dynamic data was not available. Reported figures:

| Split | Dice | IoU |
|---|---|---|
| synthetic test, 1,277 videos (2,554 frames) | 0.862 | 0.761 |

These numbers show the pipeline works end to end. **They say nothing about accuracy on real
echocardiograms**, which are noisier and far more varied than the synthetic shapes.
The web app therefore shows a "Demo model" banner whenever
`segmentation/checkpoints/*.meta.json` has `"real_data": false`.

## EF estimation

EF comes from Simpson's method of disks (20 disks) on each predicted mask:
`V = (pi/4) * sum(L_i^2 * h)`. ED = frame of maximum volume, ES = frame of minimum volume,
`EF = (EDV - ESV) / EDV * 100`. Volumes are in relative pixel^3 units (no physical
calibration), which is fine for EF because it is a ratio. Note: the printed formula in the
technical document omits the square on the diameter; the code uses the correct form.

Risk flag: >= 55 % Normal, 41-54 % Mildly Reduced, <= 40 % Reduced.

## Known limitations

- Not validated on real data (see above). Do not quote EF accuracy until it has been.
- Training uses only the two expert-labelled frames per video (ED and ES); other frames are
  unlabelled, so mask quality in mid-cycle frames is not measured.
- ED/ES are the global max/min of the volume curve: a single bad mask can distort EF.
- Assumes one apical four-chamber view with a clearly visible LV; other views, poor image
  quality, arrhythmia or very short clips give unreliable results.
- Volume is 2D-area based (single plane); real clinical EF protocols use biplane tracing.

## Reproducing / improving

See `segmentation/README.md`. To make this a real result: obtain EchoNet-Dynamic
(<https://echonet.github.io/dynamic/>), train on the full TRAIN split, evaluate on the TEST
split, replace the numbers above, then set `"real_data": true` in the metadata file.
