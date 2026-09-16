from pathlib import Path

from biomercs_ml import auto_labeler, clip_extractor, config, dataset_manifest, downloader, event_detector, hud_reader
from biomercs_ml.models import ClipRecord


def resolve_video(source: str, download_dir: Path) -> Path:
    if source.startswith("http://") or source.startswith("https://"):
        return downloader.download(source, download_dir)
    return Path(source)


def run(video_source: str, output_dir: Path, db_path: Path) -> None:
    video_path = resolve_video(video_source, output_dir / "downloads")

    timer_templates = hud_reader.load_digit_templates(config.TIMER_DIGITS_DIR)
    combo_templates = hud_reader.load_digit_templates(config.COMBO_DIGITS_DIR)
    combo_label_template = hud_reader.load_image(config.COMBO_LABEL_TEMPLATE_PATH)
    popup_digit_templates = hud_reader.load_digit_templates(config.POPUP_DIGITS_DIR)
    popup_label_template = hud_reader.load_image(config.POPUP_LABEL_TEMPLATE_PATH)

    samples = hud_reader.sample_video(
        video_path,
        timer_templates,
        combo_templates,
        combo_label_template,
        popup_digit_templates,
        popup_label_template,
    )

    sessions: dict[int, list] = {}
    for sample in samples:
        sessions.setdefault(sample.session_id, []).append(sample)

    dataset_manifest.create_db(db_path)
    clips_dir = output_dir / "clips"

    for session_id, session_samples in sessions.items():
        groups = event_detector.detect_kill_groups(session_samples, session_id, all_samples=samples)
        for group in groups:
            label = auto_labeler.label_kill_group(group)
            if label is None:
                continue

            clip_path = clips_dir / f"{video_path.stem}_{session_id}_{group.timestamp_s:.1f}.mp4"
            clip_extractor.extract_clip(video_path, group.timestamp_s, clip_path)

            record = ClipRecord(
                clip_path=str(clip_path),
                label_kind=label.kind,
                n_bonus=label.n_bonus,
                n_bullet=label.n_bullet,
                source_video=str(video_path),
                session_id=session_id,
                event_timestamp_s=group.timestamp_s,
                confidence=group.confidence,
            )
            dataset_manifest.insert_clip(db_path, record)
