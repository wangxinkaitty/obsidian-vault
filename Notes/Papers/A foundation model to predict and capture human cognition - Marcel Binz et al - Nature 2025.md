---
authors: Marcel Binz, Elif Akata, Matthias Bethge, Franziska Brändle, Fred Callaway,
  Julian Coda-Forno, Peter Dayan, Can Demircan, Maria K. Eckstein, Noémi Éltető, Thomas
  L. Griffiths, Susanne Haridi, Akshay K. Jagadish, Li Ji-An, Alexander Kipnis, Sreejan
  Kumar, Tobias Ludwig, Marvin Mathony, Marcelo Mattar, Alireza Modirshanechi, Surabhi
  S. Nath, Joshua C. Peterson, Milena Rmus, Evan M. Russek, Tankred Saanum, Johannes
  A. Schubert, Luca M. Schulze Buschoff, Nishad Singhi, Xin Sui, Mirko Thalmann, Fabian
  J. Theis, Vuong Truong, Vishaal Udandarao, Konstantinos Voudouris, Robert Wilson,
  Kristin Witte, Shuchen Wu, Dirk U. Wulff, Huadong Xiong, Eric Schulz
created: 2026-05-06
datasets:
- Psych-101
doi: 10.1038/s41586-025-09215-4
key_claims:
- Centaur predicts held-out participant behavior better than domain-specific cognitive
  models across nearly all experiments.
- Centaur generalizes to unseen cover stories, structural task modifications, and
  entirely new domains.
- Fine-tuning Centaur on human behavior improves alignment of its internal representations
  with human neural activity.
- Centaur maintains performance on standard machine learning benchmarks while becoming
  more human-like on cognitive metrics.
last_updated: 2026-05-06
limitations: []
methods:
- fine-tuning with quantized low-rank adaptation (QLoRA)
- large language model (Llama 3.1 70B)
- natural language transcription of experiments
read_status: reading
summary: Centaur, a foundation model of human cognition, is created by fine-tuning
  a large language model on Psych-101, a dataset of over 10 million human choices
  from 160 experiments. It predicts held-out participant behavior better than existing
  cognitive models and generalizes to new tasks, with internal representations aligning
  to neural activity.
tags:
- cognitive-model
- foundation-model
- large-language-model
- human-behavior
- psychology
- fine-tuning
themes:
- cognitive-psychology
- computational-neuroscience
type: paper
venue: Nature
year: 2025
zotero_key: binzFoundationModelPredict2025
---

# A foundation model to predict and capture human cognition

## Citation

Binz, M., Akata, E., Bethge, M., Brändle, F., Callaway, F., Coda-Forno, J., Dayan, P., Demircan, C., Eckstein, M. K., Éltető, N., Griffiths, T. L., Haridi, S., Jagadish, A. K., Ji-An, L., Kipnis, A., Kumar, S., Ludwig, T., Mathony, M., Mattar, M., … Schulz, E. (2025). A foundation model to predict and capture human cognition. _Nature_, _644_(8078), 1002–1009. [https://doi.org/10.1038/s41586-025-09215-4](https://doi.org/10.1038/s41586-025-09215-4)

[Open in Zotero](zotero://select/library/items/QA574ZHM)

## Abstract

Establishing a unified theory of cognition has been an important goal in psychology1,2. A first step towards such a theory is to create a computational model that can predict human behaviour in a wide range of settings. Here we introduce Centaur, a computational model that can predict and simulate human behaviour in any experiment expressible in natural language. We derived Centaur by fine-tuning a state-of-the-art language model on a large-scale dataset called Psych-101. Psych-101 has an unprecedented scale, covering trial-by-trial data from more than 60,000 participants performing in excess of 10,000,000 choices in 160 experiments. Centaur not only captures the behaviour of held-out participants better than existing cognitive models, but it also generalizes to previously unseen cover stories, structural task modifications and entirely new domains. Furthermore, the model’s internal representations become more aligned with human neural activity after fine-tuning. Taken together, our results demonstrate that it is possible to discover computational models that capture human behaviour across a wide range of domains. We believe that such models provide tremendous potential for guiding the development of cognitive theories, and we present a case study to demonstrate this.

## Highlights & annotations



## My synthesis

### Key claims

### Methods

### Limitations

### Connections to my work