---
authors: Beatrix M. G. Nielsen, Emanuele Marconato, Luigi Gresele, Andrea Dittadi,
  Simon Buchholz
created: 2026-05-06
datasets:
- SUB dataset
- CIFAR-100
- synthetic dataset
doi: 10.48550/arXiv.2602.15438
key_claims:
- Closeness in logit distance implies high linear representational similarity, while
  closeness in KL divergence does not.
- KL-based distillation can match a teacher's predictions but fail to preserve linear
  representational properties.
- Logit-distance distillation yields students with higher linear representational
  similarity and better preservation of linearly recoverable concepts.
last_updated: 2026-05-06
limitations:
- The bound from KL divergence to logit distance requires probabilities bounded away
  from zero and is not practically useful.
- The analysis is limited to a specific family of discriminative models including
  autoregressive language models.
methods:
- logit-distance distillation
- KL divergence
- linear probing
- mCCA
- representational dissimilarity measure
read_status: reading
tags:
- representational-similarity
- logit-distance
- knowledge-distillation
- identifiability
- linear-representations
- kl-divergence
type: paper
venue: null
year: 2026
zotero_key: nielsenLogitDistanceBounds2026
---

# Logit Distance Bounds Representational Similarity

## Citation

Nielsen, B. M. G., Marconato, E., Gresele, L., Dittadi, A., & Buchholz, S. (2026). _Logit Distance Bounds Representational Similarity_ (arXiv:2602.15438). arXiv. [https://doi.org/10.48550/arXiv.2602.15438](https://doi.org/10.48550/arXiv.2602.15438)

[Open in Zotero](zotero://select/library/items/FKSNLMZE)

## Abstract

For a broad family of discriminative models that includes autoregressive language models, identifiability results imply that if two models induce the same conditional distributions, then their internal representations agree up to an invertible linear transformation. We ask whether an analogous conclusion holds approximately when the distributions are close instead of equal. Building on the observation of Nielsen et al. (2025) that closeness in KL divergence need not imply high linear representational similarity, we study a distributional distance based on logit differences and show that closeness in this distance does yield linear similarity guarantees. Specifically, we define a representational dissimilarity measure based on the models' identifiability class and prove that it is bounded by the logit distance. We further show that, when model probabilities are bounded away from zero, KL divergence upper-bounds logit distance; yet the resulting bound fails to provide nontrivial control in practice. As a consequence, KL-based distillation can match a teacher's predictions while failing to preserve linear representational properties, such as linear-probe recoverability of human-interpretable concepts. In distillation experiments on synthetic and image datasets, logit-distance distillation yields students with higher linear representational similarity and better preservation of the teacher's linearly recoverable concepts.

## Highlights & annotations

**Imported: 2026-05-06**

> “ep learning models depends on the data representation they learn Bengio et al. [2013]; yet it is unclear what properties “good”” Yellow Highlight [Page ](zotero://open-pdf/library/items/EL8SJY5M?page=1&annotation=YKS8ZJ4V)

not that great

## My synthesis

### Key claims

### Methods

### Limitations

### Connections to my work