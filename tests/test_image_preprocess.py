from pathlib import Path

from PIL import Image

from app.image_preprocess import prepare_reference_image


def test_prepare_reference_image_pads_portrait_without_stretching(tmp_path: Path):
    source = tmp_path / "portrait.jpg"
    with Image.new("RGB", (1000, 1333), (20, 40, 60)) as image:
        image.save(source)

    prepared = prepare_reference_image(source, aspect_ratio="9:16", output_dir=tmp_path)

    with Image.open(prepared) as image:
        assert image.size == (1024, 1792)
        center = image.crop((0, 214, 1024, 1578))
        assert center.size == (1024, 1364)


def test_prepare_reference_image_keeps_exact_target_size_unchanged(tmp_path: Path):
    source = tmp_path / "target.png"
    with Image.new("RGB", (1024, 1792), (200, 210, 220)) as image:
        image.save(source)

    prepared = prepare_reference_image(source, aspect_ratio="9:16", output_dir=tmp_path)

    with Image.open(prepared) as image:
        assert image.size == (1024, 1792)
        assert image.getpixel((512, 896)) == (200, 210, 220)
