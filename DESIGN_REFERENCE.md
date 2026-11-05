# UI reference summary

Based on the user-provided Toss Securities and Apple captures and the NAVER market screen. These are design references, not claims about native or authenticated product states.

## HTML report

- White canvas and quiet, dense tables: Toss WTS palette and square tabs; NAVER parallel FX/rates and asset icons.
- Flat gray quote tiles and an explicit keyboard focus ring: restrained Apple-style hierarchy without marketing pills, gradients, glass, brand fonts or logos.
- See [DESIGN.md](DESIGN.md) for applied tokens. These HTML presentation rules do not change the existing desktop theme.

## Desktop app (unchanged)

- Calm dark surfaces: #101013 base, #17171c body, #202025 panels.
- Primary text #f3e9e9; secondary #a2a2ab; subtle border #35353f.
- Korean financial convention: up #f5445a, down #4391ff; show signs/text as well as color.
- Blue #4391ff for interactive emphasis, with clear labels and contrast.
- Dense but legible numeric tables, aligned numbers, explicit unit/source/actual market date.
- No ornamental shadows, loading theatre, emojis, brand logo or proprietary font redistribution.
- Use system fonts (Malgun Gothic on Windows; appropriate Korean fallback elsewhere).
- Distinguish stored values from real-time quotes and show missing-history/partial-source states clearly.
- Excel/HTML/PPTX must use the same frozen numeric snapshot; PPTX must remain editable.

The original reference contains conflicting negative-fill descriptions. This project uses readable blue down-tick text on dark backgrounds rather than black-on-black indicators.
