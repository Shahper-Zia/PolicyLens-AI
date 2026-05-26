import asyncio
from src.orchestrator import orchestrator
from src.orchestrator.orchestrator import PolicyOrchestrator

class FileLike:
	def __init__(self, path):
		self.path = path
		self.filename = path.split("/")[-1]
		with open(path, "rb") as f:
			self._data = f.read()

	def read(self):
		return self._data

# Create file-like object and call process_pdf
if __name__ == "__main__":
	policy_orchestrator = PolicyOrchestrator()
	pdf_path = "data/raw_pdfs/215824-5041653.pdf"
	mock_pdf_file = FileLike(pdf_path)
	response = asyncio.run(policy_orchestrator.process_pdf(mock_pdf_file))

	print(response)
