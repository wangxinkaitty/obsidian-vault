---
authors: []
created: 2026-05-06
datasets:
- Human Connectome Project (HCP) fMRI data
- Aging study fMRI data
doi: 10.3389/fninf.2021.740143
key_claims:
- UMAP provides higher classification accuracy than t-SNE for discriminating resting
  state from working memory tasks in embedded functional brain networks.
- t-SNE better preserves the topology of the high-dimensional functional connectivity
  space compared to UMAP.
- Functional brain networks from different studies (HCP and aging) align correctly
  in a common 2D embedding space despite differences in data collection protocols.
last_updated: '2026-05-08'
limitations:
- The study only evaluated two manifold learning techniques; other methods may perform
  differently.
- The generalizability of the findings to other tasks or populations is not established.
methods:
- t-distributed stochastic neighbor embedding (t-SNE)
- uniform manifold approximation and projection (UMAP)
- functional connectivity network construction
- classification accuracy metrics
- topology preservation metrics
read_status: reading
summary: This study evaluates t-SNE and UMAP for embedding functional brain networks
  into 2D manifolds using fMRI data from the Human Connectome Project and an aging
  study. UMAP achieves higher classification accuracy between resting state and working
  memory tasks, while t-SNE better preserves high-dimensional topology.
tags:
- fmri
- functional-connectivity
- manifold-learning
- t-sne
- umap
- neuroimaging
- machine-learning
themes:
- neuroimaging-methods
title: Embedding Functional Brain Networks in Low Dimensional Spaces Using Manifold
  Learning Techniques
type: paper
venue: Frontiers in Neuroinformatics
year: 2021
zotero_key: casanovaEmbeddingFunctionalBrain2021
---

# Embedding Functional Brain Networks in Low Dimensional Spaces Using Manifold Learning Techniques

## Citation

Casanova, R., Lyday, R. G., Bahrami, M., Burdette, J. H., Simpson, S. L., & Laurienti, P. J. (2021). Embedding Functional Brain Networks in Low Dimensional Spaces Using Manifold Learning Techniques. _Frontiers in Neuroinformatics_, _15_. [https://doi.org/10.3389/fninf.2021.740143](https://doi.org/10.3389/fninf.2021.740143)

[Open in Zotero](zotero://select/library/items/JBUH2DWA)

## Abstract

Background: fMRI data is inherently high-dimensional and difficult to visualize. A recent trend has been to find spaces of lower dimensionality where functional brain networks can be projected onto manifolds as individual data points, leading to new ways to analyze and interpret the data. Here, we investigate the potential of two powerful nonlinear manifold learning techniques for functional brain networks representation: 1) T-stochastic neighbor embedding (t-SNE) and 2) Uniform Manifold Approximation Projection (UMAP) a recent breakthrough in manifold learning.MethodsfMRI data from the Human Connectome Project (HCP) and an independent study of aging were used to generate functional brain networks. We used fMRI data collected during resting state data and during a working memory task. The relative performance of t-SNE and UMAP were investigated by projecting the networks from each study onto 2D manifolds. The levels of discrimination between different tasks and the preservation of the topology were evaluated using different metrics.ResultsBoth methods effectively discriminated the resting state from the memory task in the embedding space. UMAP discriminated with a higher classification accuracy. However, t-SNE appeared to better preserve the topology of the high-dimensional space. When networks from the HCP and aging studies were combined, the resting state and memory networks in general aligned correctly. DiscussionOur results suggest that UMAP, a more recent development in manifold learning, is an excellent tool to visualize functional brain networks. Despite dramatic differences in data collection and protocols, networks from different studies aligned correctly in the embedding space.

## Highlights & annotations



## My synthesis

### Key claims

### Methods

### Limitations

### Connections to my work