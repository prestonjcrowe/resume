# Resume Tooling

Use `build.py` to convert raw markdown resume content to a stylized PDF. Define resume content in `resume.md` and styles in `style.css`. Requires [pandoc](https://pandoc.org/installing.html).

### Usage
 
```bash
uv run build.py                    # builds resume.pdf and runs text-extraction checks
uv run build.py --show-text        # also prints what a parser would extract
uv run build.py --plain            # section headings without [BRACKETS]
```


