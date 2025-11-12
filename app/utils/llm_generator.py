from ollama import Client

class LLMGenerator:
    def __init__(self, model_name="llama2", host='http://localhost:11434'):
        """
        Initialize Llama 2 with Ollama (optimized and quantized automatically).
        No manual quantization needed - Ollama handles it!
        """
        self.client = Client(host=host)
        self.model_name = model_name
        print(f"Ollama client initialized with model: {model_name}")
        print(f"Model is ready to use (already optimized by Ollama)")

    def generate_response(self, prompt: str, system_prompt: str = None, max_tokens: int = 10000) -> str:
        """
        Generates a response from Llama 2 based on the given prompt.
        
        Args:
            prompt: User's input question/prompt
            system_prompt: Optional system instruction
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            Generated response text
        """
        # Build messages
        messages = []
        
        if system_prompt:
            messages.append({
                'role': 'system',
                'content': system_prompt
            })
        
        messages.append({
            'role': 'user',
            'content': prompt
        })
        
        # Generate response using chat endpoint
        response = self.client.chat(
            model=self.model_name,
            messages=messages,
            options={
                'num_predict': max_tokens,
                'temperature': 0.7,
                'top_p': 0.9
            }
        )
        
        return response['message']['content'].strip()
    
    def generate_simple(self, prompt: str, max_tokens: int = 100) -> str:
        """
        Simple generation without chat formatting (for one-off queries).
        """
        response = self.client.generate(
            model=self.model_name,
            prompt=prompt,
            options={
                'num_predict': max_tokens,
                'temperature': 0.7
            }
        )
        
        return response['response'].strip()
