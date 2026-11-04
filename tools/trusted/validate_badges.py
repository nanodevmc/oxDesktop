import json
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parents[2]
    badges_file = root / "badges.json"
    if not badges_file.exists():
        print(f"Error: {badges_file} does not exist", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(badges_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error parsing badges.json: {e}", file=sys.stderr)
        sys.exit(1)

    required_keys = ["types", "users", "channels"]
    for key in required_keys:
        if key not in data:
            print(f"Error: Missing required key '{key}' in badges.json", file=sys.stderr)
            sys.exit(1)

    if not isinstance(data["users"], list):
        print("Error: 'users' must be a list in badges.json", file=sys.stderr)
        sys.exit(1)

    for idx, user in enumerate(data["users"]):
        if "id" not in user or "type" not in user:
            print(f"Error: User entry #{idx} missing 'id' or 'type'", file=sys.stderr)
            sys.exit(1)

    if "trusted" in data:
        if not isinstance(data["trusted"], list):
            print("Error: 'trusted' must be a list in badges.json", file=sys.stderr)
            sys.exit(1)
        for idx, item in enumerate(data["trusted"]):
            if "id" not in item:
                print(f"Error: Trusted source entry #{idx} missing 'id'", file=sys.stderr)
                sys.exit(1)

    print("badges.json validation passed successfully.")

if __name__ == "__main__":
    main()
