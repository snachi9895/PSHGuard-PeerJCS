# Published model attachment

The frozen model archive is published on Zenodo: https://doi.org/10.5281/zenodo.24038283 (version 1.0.0; record https://zenodo.org/records/24038283). The version DOI identifies the actual files used here. The concept DOI 10.5281/zenodo.24038282 identifies the version family.

PSHGuard_PeerJCS_models_v1_20261107.zip contains six original checkpoints, pinned config/tokenizer files, historical run metadata, frozen fusion deployment parameters, original HGT source references, licence texts and checksums. Its size is 1,801,443,603 bytes and SHA256 is 683b8d89aac8378a6711f7298a245e14d1b1f9b93c7eb9cc77269e78825e3923. Download it from the record manually, then run `python3 tools/check_model_archive.py /path/to/the/model.zip` to check the downloaded ZIP bytes without loading a model. Citation files are under citations/.

The authors approved three HGT checkpoints under MIT and three ModernBERT fine-tunes under Apache-2.0 on 2026-11-07. Attribution and fine-tuning notices are preserved. These model grants are separate from the code licence. The pinned base ModernBERT weights remain an external upstream dependency.

DataCite registration and the DOI redirect were verified. The author confirmed the Open record and a browser download. Automated access from the verification network was blocked by Zenodo; no independent anonymous full-file download is claimed. The published model ZIP was not repacked after publication.

Final checkpoints use the practical HGT model. The retained RCBER class is a historical comparison arm. Source bindings and local imports are recorded in metadata/FINAL_HGT_SOURCE_BINDING.json. No checkpoint was deserialized or evaluated during this archive update. Original package archives and derived graph/token caches are outside the model attachment.
