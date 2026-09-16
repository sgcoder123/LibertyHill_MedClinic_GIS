from pathlib import Path


def main() -> None:
    output_dir = Path("data/processed/suitability")
    output_dir.mkdir(parents=True, exist_ok=True)
    print("Suitability model placeholder. Add normalized factor scoring and weighted overlay logic here.")


if __name__ == "__main__":
    main()