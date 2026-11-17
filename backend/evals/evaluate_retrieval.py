import json
from pathlib import Path

from app.services import kb_service


def has_evidence(chunks: list[dict], evidence: dict) -> bool:
    for chunk in chunks:
        if (
            chunk["source"] == evidence["source"]
            and evidence["quote"] in chunk["content"]
        ):
            return True

    return False


def run_evaluation():
    dataset_path = Path(__file__).with_name("rag_cases.json")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    cases = [case for case in dataset["cases"] if case["expected_behavior"] == "answer"]
    if not cases:
        raise ValueError("题库中没有资料内问题")

    results = []
    passed = 0

    for case in cases:
        chunks = kb_service.search_chunks(case["question"])

        missing = [
            evidence
            for evidence in case["evidence"]
            if not has_evidence(chunks, evidence)
        ]

        covered = not missing
        passed += int(covered)

        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "passed": covered,
                "missing_evidence": missing,
                "chunks": chunks,
            }
        )

        status = "PASS" if covered else "MISS"
        print(f"{case['id']} {status}: {case['question']}")

    report = {
        "total": len(cases),
        "passed": passed,
        "coverage": passed / len(cases),
        "results": results,
    }

    report_path = dataset_path.with_name("retrieval_report.json")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"完整依据覆盖：{passed}/{len(cases)}")
    print(f"结果已保存：{report_path}")
    return report


if __name__ == "__main__":
    run_evaluation()
