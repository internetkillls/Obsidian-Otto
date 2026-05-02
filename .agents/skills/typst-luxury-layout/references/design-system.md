# Typst Luxury Layout — Reference

## Status

Initial reference. To be populated with design system decisions and precedent layouts as this skill is used.

## Design system decisions

### Typography

(To be populated with font choices and sizing rationale.)

### Grid and spacing

(To be populated with grid system and spacing parameters.)

### Color palette

(To be populated with color choices and rationale.)

## Known layouts

(To be populated with precedent Typst layout examples.)

### Template: layout card

```markdown
## [Layout Name]

**Use case:** [what this layout is for]
**Typst template:** [reference to .typ file]

**Parameters:**
- Font: [family and size]
- Margins: [top right bottom left]
- Grid: [columns and gutter]
- Special: [headers, footers, etc.]

**Source precedent:** [file path if grounded in a vault note]
```

## Cross-format conversion

### Markdown → Typst → PDF

```bash
# Manual conversion
pandoc input.md -o output.typ --to typst
typst compile output.typ output.pdf

# Direct Typst
typst compile document.typ output.pdf
```

### Mermaid → SVG

```bash
mmdc -i diagram.mmd -o diagram.svg
```

### LaTeX → Typst

(Requires case-by-case review. Not all LaTeX packages have Typst equivalents.)

## Verification checklist

- [ ] PDF opens without errors
- [ ] Typography matches specified parameters
- [ ] Layout is consistent across pages
- [ ] No overflow or clipping
- [ ] Source content is faithfully represented
