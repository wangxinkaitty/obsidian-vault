---
type: paper
authors: {{authors}}
year: {{date | format("YYYY")}}
venue: {{publicationTitle}}
doi: {{DOI}}
zotero_key: {{citekey}}
methods: []
datasets: []
key_claims: []
limitations: []
tags: []
read_status: reading
last_updated: {{importDate | format("YYYY-MM-DD")}}
---

# {{title}}

## Citation

{{bibliography}}

[Open in Zotero](zotero://select/library/items/{{itemKey}})

## Abstract

{{abstractNote}}

## Highlights & annotations

{% for annotation in annotations -%}
> {{annotation.annotatedText}} ([p. {{annotation.pageLabel}}](zotero://open-pdf/library/items/{{annotation.attachment.itemKey}}?page={{annotation.pageLabel}}&annotation={{annotation.id}}))

{% if annotation.comment %}**Note:** {{annotation.comment}}{% endif %}

{% endfor %}

## Notes from Zotero

{% for note in notes -%}
{{note}}

---

{% endfor %}

## My synthesis

### Key claims

### Methods

### Limitations

### Connections to my work