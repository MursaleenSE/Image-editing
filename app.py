import streamlit as st
from PIL import Image
import io
import base64
import requests
import os

st.set_page_config(page_title="PhotoStyler", layout="centered")

st.title("PhotoStyler — upload a selfie, pick a style, get a portrait/cartoonic result")

# Upload
uploaded = st.file_uploader("Upload an image (jpg/png)", type=["jpg","jpeg","png"])
if not uploaded:
    st.info("Upload a photo to begin.")
    st.stop()

img = Image.open(uploaded).convert("RGB")
st.image(img, caption="Input image", use_column_width=True)

# Choose style
style = st.selectbox("Pick a style", ["Cartoon", "Oil painting", "Portrait / Studio", "Anime", "Pop-art"])
strength = st.slider("Transformation strength (higher = more change)", min_value=0.0, max_value=1.0, value=0.6)

if st.button("Transform"):
    with st.spinner("Calling model..."):
        # Example using Replicate's stable-diffusion-img2img model via their REST API.
        # You need to set REPLICATE_API_TOKEN in Streamlit secrets as st.secrets["api_keys"]["REPLICATE_API_TOKEN"]
        token = st.secrets["api_keys"]["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"]

        # Convert image to bytes and base64 if needed
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        # For Replicate we typically upload the image (multipart) and call the model.
        # Simpler approach: use replicate python client (if installed) OR call their REST.
        # Below is a lightweight REST call to Replicate's predictions endpoint:
        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }

        # Choose model and prompt per style
        prompt_map = {
            "Cartoon": "Convert this photo into a high-quality, colorful cartoon portrait, smooth lines, simplified shapes",
            "Oil painting": "Create a classic oil painting style portrait from this input photo, painterly brush strokes, rich texture",
            "Portrait / Studio": "Create a professional studio portrait from this input photo with soft lighting and neutral background",
            "Anime": "Convert this photo into an anime-style character, large expressive eyes, simplified shading",
            "Pop-art": "Create a pop-art style portrait with bold colors and halftone patterns"
        }
        prompt = prompt_map[style]

        # Using "stability-ai/stable-diffusion-img2img" on Replicate (public model)
        # POST to https://api.replicate.com/v1/predictions
        payload = {
            "version": "a9758d8b3f3b3c03d9b2b7f8a6f7c9c1b0d0e9a1", # placeholder version - ideally use the model's latest version id
            "input": {
                "image": "data:image/png;base64," + base64.b64encode(img_bytes).decode(),
                "prompt": prompt,
                "strength": float(strength),
                "num_inference_steps": 28
            }
        }

        # NOTE: The exact 'version' id and input keys depend on the model; consult Replicate model page for exact fields.
        resp = requests.post("https://api.replicate.com/v1/predictions", json=payload, headers=headers)
        if resp.status_code not in (200, 201):
            st.error(f"API error: {resp.status_code} - {resp.text}")
        else:
            result = resp.json()
            # Replicate returns a prediction object that may run async; for simplicity, poll until completed.
            prediction_url = f"https://api.replicate.com/v1/predictions/{result['id']}"
            import time
            while True:
                r = requests.get(prediction_url, headers=headers)
                rj = r.json()
                status = rj.get("status")
                if status == "succeeded":
                    output_urls = rj["output"]
                    # output may be list of URLs
                    out_url = output_urls[0]
                    st.image(out_url, caption="Transformed result", use_column_width=True)
                    st.markdown(f"[Download result]({out_url})")
                    break
                elif status == "failed":
                    st.error("Model failed: " + str(rj))
                    break
                else:
                    time.sleep(1)
                    # continue polling
