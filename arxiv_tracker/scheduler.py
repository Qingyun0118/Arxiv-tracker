from __future__ import annotations
import time
import click
import schedule
from .config import Settings
from .query import build_search_query
from .client import fetch_arxiv_feed
from .parser import parse_feed
from .output import save_json, save_markdown

def _job(cfg: Settings, out_dir: str):
    q = build_search_query(
        categories=cfg.categories,
        keywords=cfg.keywords,
        exclude_keywords=cfg.exclude_keywords,
        logic=cfg.logic,
        keyword_expression=getattr(cfg, "keyword_expression", ""),
    )
    print(f"[Scheduler] Running query: {q}")
    xml = fetch_arxiv_feed(q, start=0, max_results=cfg.max_results,
                           sort_by=cfg.sort_by, sort_order=cfg.sort_order)
    items = parse_feed(xml)
    jp = save_json(items, out_dir)
    mp = save_markdown(items, out_dir)
    print(f"[Scheduler] Saved: {jp}")
    print(f"[Scheduler] Saved: {mp}")

@click.command()
@click.option("--time", "time_str", required=True, help="每日触发时间，如 09:00")
@click.option("--config", "config_path", type=click.Path(exists=True), required=True, help="配置文件路径（YAML）")
@click.option("--out-dir", default="outputs", help="输出目录")
def main(time_str, config_path, out_dir):
    cfg = Settings.from_file(config_path)
    schedule.every().day.at(time_str).do(_job, cfg=cfg, out_dir=out_dir)
    print(f"[Scheduler] Registered daily job at {time_str}. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
