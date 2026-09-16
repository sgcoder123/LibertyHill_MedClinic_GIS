from pathlib import Path


def main() -> None:
    output_dir = Path("data/raw/census")
    output_dir.mkdir(parents=True, exist_ok=True)
    print("Census download pipeline placeholder. Add ACS 5-year block-group and TIGER geometry download logic here.")


if __name__ == "__main__":
    main()