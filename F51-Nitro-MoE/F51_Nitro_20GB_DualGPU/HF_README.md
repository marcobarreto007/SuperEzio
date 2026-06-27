# Mixtral 8x7B Local Runtime Notes

This kit is currently focused on Mixtral 8x7B Instruct Q4_K_M.

Use:

```bat
START_MIXTRAL_FINANCE.bat
```

Important runtime note:

- `bin\llama-server.exe` is the newer F51 runtime.
- `bin_mixtral_legacy\llama-server.exe` is the Mixtral-compatible runtime.

The downloaded Mixtral GGUF fails on the newer runtime with:

```text
missing tensor 'blk.0.ffn_down_exps.weight'
```

The legacy `llama.cpp b3989` runtime loads it successfully and produced about `14 tok/s` decode locally with `-ngl 18`.
