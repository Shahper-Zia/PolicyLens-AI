import asyncio
import os
import time
from src.orchestrator import orchestrator
from src.orchestrator.orchestrator import PolicyOrchestrator
from src.orchestrator.chunker.relevant_chunker import get_brand_indication_chunks
from src.LLMS.llama_caller import call_llama
import pandas as pd
from tqdm import tqdm
import numpy as np

class Rules:

	def __init__(self, rules_folder="C:\\Users\\MD AREEB  AKHTAR\\PolicyLens-AI\\rules"):
		rule_files = [f for f in os.listdir(rules_folder) if f.endswith(".md")]
		self.rules = {}
		for rule_file in rule_files:
			with open(f"{rules_folder}/{rule_file}", "r", encoding="utf-8") as f:
				self.rules[rule_file] = f.readlines()
			self.rules[rule_file] = [line.strip() for line in self.rules[rule_file] if line.strip()]
			self.rules[rule_file] = [" ".join(x) for x in self.rules[rule_file]]
		print(f"Loaded rules: {list(self.rules.keys())}")

	def get_rule(self, rule_name):
		return self.rules.get(rule_name, "")

class FileLike:
	def __init__(self, path,chunk_size):
		self.path = path
		self.filename = path.split("/")[-1]
		with open(path, "r", encoding="utf-8") as f:
			self._data = f.readlines()
		self._data = [line.strip() for line in self._data if line.strip()]
		self._data = [line[x: x + chunk_size] for line in self._data for x in range(0, len(line), chunk_size)]
		self._data = [" ".join(x) for x in self._data]
	def read(self):
		return self._data

# Create file-like object and call process_markdown
if __name__ == "__main__":
	policy_orchestrator = PolicyOrchestrator()
	#pdf_path = "data/raw_pdfs/215824-5041653.pdf"
	md_path = "C:\\Users\\MD AREEB  AKHTAR\\PolicyLens-AI\\data\\extracted_pdfs_mds\\148593-4960549.md"
	rule_mapper = Rules()
	chunk_size = 300
	input_csv = "C:\\Users\\MD AREEB  AKHTAR\\PolicyLens-AI\\submissions.csv"
	df = pd.read_csv(input_csv)
	print(df.columns)
	file_names = df.iloc[:, 0].tolist()
	file_names = [name[:-4] for name in file_names]
	brand_names = df.iloc[:, 1].tolist()
	result_df = []
	output_file = "output.csv"
	output_exists = os.path.exists(output_file)
	for file_name, brand_name in tqdm(zip(file_names, brand_names)):
		print(f"Processing {file_name} for brand {brand_name}")
		file_path = f"C:\\Users\\MD AREEB  AKHTAR\\PolicyLens-AI\\data\\extracted_pdfs_mds\\{file_name}.md"
		with open(file_path, "r", encoding="utf-8") as f:
			file_text = f.read()
		mock_md_file_chunks = get_brand_indication_chunks(file_text, [brand_name])
		brand_payload = mock_md_file_chunks.get(brand_name, {}) if isinstance(mock_md_file_chunks, dict) else {}
		chunks = brand_payload.get("chunks", []) if isinstance(brand_payload, dict) else []
		if not chunks:
			chunks = FileLike(file_path, chunk_size).read()
		cur_dict = {}
		for rule_name in rule_mapper.rules.keys():
			responses = []
			for chunk in chunks:
				chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
				response = call_llama(
					f"what is the value of {rule_name} for the {brand_name} strictly according to the document:{chunk_text}? CONTEXT: {rule_mapper.get_rule(rule_name)}"
				)
				time.sleep(np.random.randint(1,10))	

				responses.append(response)
				print("######-----------------------##########")
				print(response)
			final_response = str(responses)
			response = call_llama(
				f"Given the following responses for a question about the rule {rule_name} for the brand {brand_name}, extract the most probable value for the rule strictly according to the document. If there are multiple values, list them all. Responses: {final_response}"
			)
			time.sleep(1)
			print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
			print(response)
			cur_dict[rule_name] = response
			output_df = pd.DataFrame({"file_name": [file_name], "brand_name": [brand_name], "response": [response]})
			if not output_exists:
				output_df.to_csv(output_file, index=False)
				output_exists = True
			else:
				output_df.to_csv(output_file, mode="a", index=False, header=False)
			
		print(cur_dict)
		result_df.append(cur_dict)
	result_df = pd.DataFrame(result_df)
	result_df.to_csv("extracted_parameters.csv", index=False)


	# mock_md_file = FileLike(md_path)	
	# content = mock_md_file.read()
	# question = "what is the age for the brand name STELARA?"
	# context = f"Document content: {content}\n\nQuestion: {question}"
	# response = call_llama(context)
	
	#response = asyncio.run(policy_orchestrator.process_markdown(mock_md_file))
	# print(response)
