if __name__ == "__main__":
    from extractor.run_pipeline import run_pipeline

    pdf_list = ['input/rishabh_sample_po_1.pdf', 
                'input/rishabh_sample_po_2.pdf',
                'input/RT Test data-1.pdf', 
                'input/RT Test data-1.pdf',
                'input/RT Test data-1.pdf']
    
    for pdf_file in pdf_list:
        print(f"----------PDF File: {pdf_file} ------------")
        text = run_pipeline(pdf_file)
        print(text)