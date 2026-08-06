import json
from meddraft_ai.core.llm_client import LLMClient

class MedicalWriterAgent:
    """
    Theoretical statistical writing agent: translates pre-computed JSON statistical outputs
    into publication-grade narrative sections and markdown tables strictly adhering to APA 7th edition rules.
    """
    def __init__(self):
        self.llm = LLMClient()

    def get_system_prompt(self, selected_test: str = "") -> str:
        test_instruction = f"\nPRIMARY TEST USED: {selected_test}\n" if selected_test else ""
        return (
            "You are a professional medical writer and biostatistician agent.\n"
            "Your task is to take a pre-computed JSON dataset of statistical results and translate it into a narrative section and markdown tables strictly adhering to APA 7th edition formatting rules.\n\n"
            "CRITICAL RULES:\n"
            "1. Do NOT calculate or compute any numbers. Copy all numerical results EXACTLY from the provided JSON.\n"
            "2. Never write raw JSON or code snippets in the final narrative. Output clean, publication-grade markdown.\n"
            "3. Format all statistics strictly according to APA 7th guidelines.\n"
            "4. Start the narrative with a brief section describing the statistical assumptions tested and justification for test selection.\n"
            "5. Explicitly report and interpret effect sizes qualitatively (e.g., small, medium, large effect).\n"
            + test_instruction +
            "\nAPA 7th FORMATTING RULES:\n"
            "- Descriptive: M = X.XX (SD = X.XX)\n"
            "- t-test: t(df) = X.XX, p = .XXX, d = X.XX\n"
            "- ANOVA: F(df_between, df_within) = X.XX, p = .XXX, n2 = .XXX\n"
            "- Non-parametric: Median = X [IQR: X-X], U = X.X, p = .XXX\n"
            "- Chi-Square: chi2(df, N = X) = X.XX, p = .XXX\n"
            "- Regression: beta = X.XX, SE = X.XX, t(df) = X.XX, p = .XXX; R2 = .XX\n"
            "- p-values: never write 'p = 0.000' -> write 'p < .001'; omit leading zero ('p = .045').\n"
        )

    def write_report(self, stats_json: dict, study_description: str, selected_test: str = "") -> str:
        system_prompt = self.get_system_prompt(selected_test)
        user_prompt = (
            f"Study Description: {study_description}\n"
            f"Assigned Test: {selected_test}\n"
            f"Computed Results JSON:\n{json.dumps(stats_json, indent=2)}\n\n"
            f"Please write a comprehensive Results section narrative and APA 7th table."
        )
        return self.llm.query(system_prompt, user_prompt)
