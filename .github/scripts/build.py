import mistune

with open("writeup.md") as f:
    content = f.read()

html = mistune.html(content)

with open("dist/index.html", "w") as f:
    f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>BiMBrI</title>
    <link rel="stylesheet" href="style.css">
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head>
<body>
    {html}
    <footer>
        <p>© 2026 BiMBrI contributors.
        Software: <a href="https://opensource.org/licenses/MIT">MIT License</a>.
        Content: <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.
        Unless otherwise noted.</p>
    </footer>
</body>
</html>""")
