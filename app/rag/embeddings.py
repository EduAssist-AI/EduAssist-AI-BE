from transformers import AutoTokenizer, AutoModel
import torch

class Embeddings:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)

    def get_embedding(self, text):
        encoded_input = self.tokenizer(text, padding=True, truncation=True, return_tensors='pt')
        with torch.no_grad():
            model_output = self.model(**encoded_input)
        # Mean pooling to get a single vector
        sentence_embeddings = model_output.last_hidden_state.mean(dim=1)
        return sentence_embeddings.tolist()[0]