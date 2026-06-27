# LTX-Video 2.3 + Sulfur2 Model Requirements

## Summary
Comprehensive requirements for running LTX-Video 2.3 with Sulfur2 enhancement in ComfyUI on Google Colab.

## Model Files (Complete List)

### Core Models (Required)
| Model | Size | Path | URL |
|-------|------|------|-----|
| ltx-video-2.3.safetensors | 14.2GB | `models/checkpoints/` | [HuggingFace](https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2.3.safetensors) |
| ltx-vae-2.3.safetensors | 1.6GB | `models/vae/` | [HuggingFace](https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-vae-2.3.safetensors) |
| tokenizer.model | ~1MB | `models/text_encoders/` | [HuggingFace](https://huggingface.co/Lightricks/LTX-Video/resolve/main/tokenizer/tokenizer.model) |
| ltx-2-19b-embeddings_connector_distill_bf16.safetensors | ~1GB | `models/text_encoders/` | [HuggingFace](https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-2-19b-embeddings_connector_distill_bf16.safetensors) |

### Text Encoder (Required)
| Model | Size | Path |
|-------|------|------|
| gemma-3-12b-it-Q4_K_S.gguf | 7GB | `models/text_encoders/` |
| gemma-3-12b-it-Q4_K_M.gguf | 9GB | `models/text_encoders/` (higher quality) |

### Enhancement Models (Optional)
| Model | Size | Path | Purpose |
|-------|------|------|---------|
| sulfur2-enhancer.safetensors | 3.8GB | `models/lora/` | Detail enhancement, color saturation |
| ltx-2-spatial-upscaler-x2-1.0.safetensors | ~2GB | `models/latent_upscale_models/` | Spatial upscaling |

## ComfyUI Plugins

### Required
- **ComfyUI-LTXVideo** - Official LTX-Video nodes
- **ComfyUI-VideoHelperSuite** - Video loading/saving
- **ComfyUI-Manager** - Plugin management

### Recommended
- **ComfyUI-GGUF** - GGUF quantized model support (for <12GB VRAM)
- **ComfyUI-Crystools** - VRAM/RAM monitoring
- **ComfyUI-KJNodes** - LTX GGUF workflow helpers

## Workflow Node Structure
```
1. LTX Video Loader → ltx-video-2.3.safetensors
2. LTX VAE Loader → ltx-vae-2.3.safetensors
3. CLIP Text Encode (Positive)
4. CLIP Text Encode (Negative)
5. LTX Video Sampler (width:1280, height:768, frames:121, steps:30, cfg:4.5)
6. LoRA Loader → sulfur2-enhancer.safetensors (strength: 0.8)
7. VAE Decode
8. Video Save
```

## Key Parameters
- **Resolution**: 1280x768 (must be multiple of 32)
- **Frames**: 121 (5 seconds @ 24fps)
- **Steps**: 30 (range: 20-50)
- **CFG**: 4.5 (range: 3.0-6.0)
- **Sampler**: euler
- **Sulfur2 LoRA Strength**: 0.8 (range: 0.6-1.0)

## Low VRAM Optimization (<12GB)
For 8GB VRAM (Colab T4, RTX 3060/4060):
1. Use GGUF quantized models (Q4_K_M or Q4_K_S)
2. Install ComfyUI-GGUF plugin
3. Add `--lowvram` to ComfyUI startup
4. Reduce resolution if needed (768x512)

## Python Dependencies
```bash
pip install ltx-video==2.3.0
pip install diffusers>=0.28.0
pip install transformers>=4.40.0
pip install av==10.0.0
```

## Common Issues
- **OOM Error**: Reduce resolution, use GGUF, add --lowvram
- **Sulfur2 ineffective**: Increase strength to 0.9-1.0
- **Video flickering**: Increase steps to 35-40, reduce CFG to 3.5-4.0

## References
- [LTX-Video Official](https://github.com/Lightricks/LTX-Video)
- [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)
- [Kijai ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF)
- [HuggingFace LTX-Video](https://huggingface.co/Lightricks/LTX-Video)
