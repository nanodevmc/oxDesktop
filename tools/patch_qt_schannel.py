import os
import sys

def patch_file(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return False
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    target = 'if (QT_VERSION GREATER 6)'
    replacement = 'if (QT_VERSION_MAJOR GREATER_EQUAL 6)'
    
    if target in content:
        content = content.replace(target, replacement)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Patched {path}")
        return True
    elif replacement in content:
        print(f"Already patched: {path}")
        return True
    else:
        print(f"Target pattern not found in {path}")
        return False

if __name__ == '__main__':
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    qt_cmake = os.path.join(base_dir, 'cmake', 'external', 'qt', 'CMakeLists.txt')
    patch_file(qt_cmake)
