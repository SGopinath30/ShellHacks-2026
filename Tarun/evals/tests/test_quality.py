from evals.quality import evaluate_rows


def test_quality_reports_detection_and_field_accuracy() -> None:
    gold = [
        {
            "case_id": "one",
            "projects": [
                {"project_name": "North Ridge", "status": "planned", "voltage_kv": 115}
            ],
        }
    ]
    predictions = [
        {
            "case_id": "one",
            "projects": [
                {"project_name": "North Ridge", "status": "proposed", "voltage_kv": 115}
            ],
        }
    ]

    metrics = evaluate_rows(gold, predictions, fields=("status", "voltage_kv"))

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.field_accuracy == 0.5


def test_duplicate_prediction_is_counted_as_false_positive() -> None:
    project = {"project_name": "North Ridge"}
    metrics = evaluate_rows(
        [{"case_id": "one", "projects": [project]}],
        [{"case_id": "one", "projects": [project, project]}],
        fields=("project_name",),
    )

    assert metrics.true_positives == 1
    assert metrics.false_positives == 1
