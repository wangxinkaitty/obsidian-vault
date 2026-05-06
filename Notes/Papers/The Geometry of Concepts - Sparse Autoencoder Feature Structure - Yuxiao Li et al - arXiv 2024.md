---
authors: Yuxiao Li, Eric J. Michaud, David D. Baek, Joshua Engels, Xiaoqing Sun, Max
  Tegmark
created: 2026-05-06
datasets:
- Gemma Scope SAE features (Gemma-2-2b, Gemma-2-9b)
- Todd et al. (2023) function vector dataset
doi: 10.48550/arXiv.2410.19750
key_claims:
- SAE feature point clouds contain 'crystals'—parallelogram and trapezoid structures—that
  generalize the classic (man, woman, king, queen) analogy.
- Projecting out global distractor directions (e.g., word length) using linear discriminant
  analysis significantly improves the quality of these crystal structures.
- SAE features exhibit functional modularity at intermediate scales, forming 'lobes'
  (e.g., math/code vs. English) that are spatially localized beyond random expectation.
- The large-scale structure of the feature point cloud follows a power-law eigenvalue
  spectrum, with the steepest slope in middle layers, and clustering entropy varies
  by layer.
last_updated: 2026-05-06
limitations:
- Initial search for SAE crystals found mostly noise until distractor directions were
  removed.
- The study is limited to Gemma-2 models and specific SAE configurations; generalizability
  to other models is not tested.
methods:
- sparse autoencoders
- linear discriminant analysis
- principal component analysis
- t-SNE
- clustering (k-means, hierarchical)
- silhouette score
read_status: reading
summary: 'Sparse autoencoder features in large language models exhibit geometric structure
  at three scales: atomic ''crystals'' (parallelograms/trapezoids), intermediate ''brain
  lobes'' (functional modularity), and large-scale power-law eigenvalue spectra. The
  paper demonstrates that projecting out distractor directions (e.g., word length)
  via linear discriminant analysis improves crystal quality, and quantifies spatial
  locality of feature clusters.'
tags:
- sparse-autoencoders
- large-language-models
- concept-representation
- geometric-structure
- analogical-reasoning
- functional-modularity
- linear-discriminant-analysis
themes:
- representation-learning
type: paper
venue: ''
year: 2024
zotero_key: liGeometryConceptsSparse2024
---

# The Geometry of Concepts: Sparse Autoencoder Feature Structure

## Citation

Li, Y., Michaud, E. J., Baek, D. D., Engels, J., Sun, X., & Tegmark, M. (2024). _The Geometry of Concepts: Sparse Autoencoder Feature Structure_ (arXiv:2410.19750). arXiv. [https://doi.org/10.48550/arXiv.2410.19750](https://doi.org/10.48550/arXiv.2410.19750)

[Open in Zotero](zotero://select/library/items/G9D5D7W4)

## Abstract

Sparse autoencoders have recently produced dictionaries of high-dimensional vectors corresponding to the universe of concepts represented by large language models. We find that this concept universe has interesting structure at three levels: 1) The "atomic" small-scale structure contains "crystals" whose faces are parallelograms or trapezoids, generalizing well-known examples such as (man-woman-king-queen). We find that the quality of such parallelograms and associated function vectors improves greatly when projecting out global distractor directions such as word length, which is efficiently done with linear discriminant analysis. 2) The "brain" intermediate-scale structure has significant spatial modularity; for example, math and code features form a "lobe" akin to functional lobes seen in neural fMRI images. We quantify the spatial locality of these lobes with multiple metrics and find that clusters of co-occurring features, at coarse enough scale, also cluster together spatially far more than one would expect if feature geometry were random. 3) The "galaxy" scale large-scale structure of the feature point cloud is not isotropic, but instead has a power law of eigenvalues with steepest slope in middle layers. We also quantify how the clustering entropy depends on the layer.

## Highlights & annotations



## My synthesis

### Key claims

### Methods

### Limitations

### Connections to my work