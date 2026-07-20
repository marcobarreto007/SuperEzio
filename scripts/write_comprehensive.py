import pathlib, sys
lines = []
for line in sys.stdin:
    lines.append(line.rstrip(chr(92)+chr(110)))
p = pathlib.Path("C:/Users/marco/Desktop/SuperEzio/scripts/comprehensive_ui_test.py")
p.write_text(chr(10).join(lines))
print(f"Written {len(lines)} lines")
