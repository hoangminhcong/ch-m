"""
Kiểm hạn mức của một API key: gửi MỘT request rất ngắn và in mã trạng thái + các header hạn mức (x-ratelimit-*,
retry-after) mà nhà cung cấp trả về. Không in key. Tốn vài chục token.

Chạy:  python scripts/check_api_quota.py --provider cerebras --key-var CEREBRAS_API_KEY_2
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_cap_generation import PROVIDERS  # noqa: E402

RATE_HEADERS = ("retry-after",)


def _print_headers(headers) -> None:
    shown = {k: v for k, v in dict(headers).items() if k.lower().startswith("x-ratelimit") or k.lower() in RATE_HEADERS}
    if not shown:
        sys.stdout.write("  (nhà cung cấp không gửi header hạn mức)\n")
    for k, v in sorted(shown.items()):
        sys.stdout.write(f"  {k}: {v}\n")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--provider", choices=sorted(PROVIDERS), default="cerebras")
    p.add_argument("--key-var", required=True, help="tên biến key trong .env, VD CEREBRAS_API_KEY_2")
    p.add_argument("--max-tokens", type=int, default=32, help="giới hạn độ dài câu trả lời gửi kèm request")
    p.add_argument("--no-max", action="store_true",
                   help="KHÔNG gửi giới hạn độ dài — đúng như run_cap_generation đang gọi (để thử nhà cung cấp có tính "
                        "phần trả lời tối đa vào hạn mức token / phút không)")
    p.add_argument("--prompt-chars", type=int, default=0,
                   help="độn prompt tới khoảng N ký tự (VD 28000 = cỡ prompt của R1307:Art43(9)) để thử request dài")
    args = p.parse_args()
    from dotenv import load_dotenv
    from openai import APIStatusError, OpenAI

    load_dotenv(PROJECT_ROOT / ".env")
    key = os.environ.get(args.key_var)
    if not key:
        raise SystemExit(f"Không có biến {args.key_var} trong .env")
    base_url, model = PROVIDERS[args.provider]
    client = OpenAI(base_url=base_url, api_key=key, max_retries=0)
    limit = {} if args.no_max else {"max_completion_tokens": args.max_tokens}
    sys.stdout.write(f"Giới hạn độ dài câu trả lời: {'KHÔNG gửi (như run_cap_generation)' if args.no_max else args.max_tokens}\n")
    filler = "The Member State shall check the application before payment. " * (args.prompt_chars // 62)
    content = (f"Ignore the following text.\n{filler}\n" if filler else "") + "Reply with OK."
    sys.stdout.write(f"Độ dài prompt: {len(content)} ký tự\n")
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=model, messages=[{"role": "user", "content": content}], **limit)
        sys.stdout.write(f"{args.key_var}: HTTP {raw.http_response.status_code} — key dùng được ngay lúc này\n")
        usage = raw.parse().usage
        if usage is not None:
            sys.stdout.write(f"  token đã dùng: vào {usage.prompt_tokens}, ra {usage.completion_tokens}\n")
        _print_headers(raw.headers)
    except APIStatusError as exc:
        sys.stdout.write(f"{args.key_var}: HTTP {exc.status_code} — {str(exc)[:300]}\n")
        _print_headers(exc.response.headers)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
