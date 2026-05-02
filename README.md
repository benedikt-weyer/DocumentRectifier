# Document Rectifier

Interactive OpenCV utility that rectifies document photos from the `in/` folder and saves the cropped result into a timestamped directory under `out/`.

## Setup

```bash
uv sync
```

## Run

```bash
uv run document-rectifier
```

## Controls

- The script starts a local web page on `http://127.0.0.1:<port>` and tries to open it automatically.
- Click four corners on the displayed image.
- `Save Crop`: rectify and save the current image.
- `Reset`: clear the selected points for the current image.
- `Skip`: leave the current image untouched.
- `Quit`: stop processing early.

The output size is determined from the selected quadrilateral for each image, so the aspect ratio is computed per image rather than fixed globally.