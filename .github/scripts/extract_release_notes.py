import sys
import re

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'changelog.txt'
    dst = sys.argv[2] if len(sys.argv) > 2 else 'release_notes.md'
    
    try:
        with open(src, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        with open(dst, 'w', encoding='utf-8') as f:
            f.write("oxDesktop Release\n")
        return
        
    out = []
    ver_count = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\d+\.\d+(\.\d+)*', stripped):
            ver_count += 1
            if ver_count > 1:
                break
        if ver_count >= 1:
            out.append(line)
            
    content = "".join(out).strip()
    if not content:
        content = "oxDesktop Release"
        
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(content + "\n")

if __name__ == '__main__':
    main()
