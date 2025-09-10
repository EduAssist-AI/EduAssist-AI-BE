from transformers import pipeline

class LLMGenerator:
    def __init__(self, model_name="google/flan-t5-small"):
        print(f"Loading LLM model: {model_name}...")
        self.generator = pipeline("text2text-generation", model=model_name)
        print(f"LLM model {model_name} loaded successfully.")

    def generate_response(self, prompt: str) -> str:
        """
        Generates a response from the LLM based on the given prompt.
        """
        # For T5 models, the output is a list of dictionaries, we need the 'generated_text'
        response = self.generator(prompt, max_new_tokens=100, num_return_sequences=1)
        return response[0]['generated_text']