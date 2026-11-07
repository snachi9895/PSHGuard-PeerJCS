# Third-party sources and scope

This record describes external inputs. It does not grant new rights to them or place them under the PSHGuard MIT software licence. The original archives, upstream model weights and dependency libraries are not bundled in the current GitHub preparation draft.

## Datadog malicious software packages dataset

- Source: https://github.com/DataDog/malicious-software-packages-dataset
- Used source revision: bd451196cdc0ef299e147c9b1a793ede76637d08.
- The upstream snapshot contains Apache-2.0 LICENSE and NOTICE. Copies in this distribution preserve their bytes; they were also identical to the retrieved main-branch notices on 2026-11-07.
- Copyright and notices are retained in third_party/Datadog/LICENSE and third_party/Datadog/NOTICE.
- The sample access index links original source archives; it does not redistribute or relicense the contents of individual software packages.

## Guo source registry

- Source: https://github.com/lxyeternal/pypi_malregistry
- Used source revision: 5f33333e64aa384ab12e707c7eb5f4f6d1acf25a.
- No blanket licence file was identified at the root of the inspected snapshot. Preserve the upstream citation and exact paths. A publicly visible source archive does not itself establish permission to relicense or mirror that archive.
- This observation is limited to the inspected records and is not a conclusion about every individual package's rights.

## PyPI source distributions

- Metadata service: https://pypi.org/pypi/<name>/<version>/json
- Match the recorded source filename and SHA256, retaining each package's original terms. The project software licence does not cover these third-party distributions.
- The access-index URLs have not been live-tested in this audit.

## ModernBERT

- Source: https://huggingface.co/answerdotai/ModernBERT-base
- Used revision: 8949b909ec900327062f0ebf497f51aef5e6f0c8.
- The model card at that exact revision declares Apache-2.0: https://huggingface.co/answerdotai/ModernBERT-base/raw/8949b909ec900327062f0ebf497f51aef5e6f0c8/README.md
- The base model remains an upstream dependency. Any distribution of derived checkpoints must preserve applicable upstream terms and clearly identify the PSHGuard fine-tuning modifications.
- Base-model access and the six research checkpoint records are listed separately in metadata/MODEL_ACCESS_PLAN.csv. That file is an access plan, not a public download claim.

## EA4MP reproduction and software dependencies

- Method source: https://github.com/EA4MP/EA4MP at revision 66fe6087af99b41fc56e5053c508bfb774a036a7.
- The uploaded ea4mp_repro module is recorded as a local independent reproduction/normalization implementation; the full upstream EA4MP repository is not bundled.
- An exact-byte comparison of nontrivial Python files found no identical upstream file. That comparison does not establish authorship or rule out adaptation. The authors have separately confirmed authority to release the main software under MIT; existing upstream terms remain applicable.
- Python, PyTorch, PyTorch Geometric, Transformers and other installed dependencies keep their own licences. A requirements list does not redistribute those libraries or replace their terms.

The root MIT License applies within docs/LICENSE_SCOPE.md. This notice grants no new rights to third-party materials, data or weights, and assigns no DOI.
