(ns app.views.revops.ev-bonus-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.views.revops.ev-bonus :as ev-bonus]))

(deftest numeric-contract-test
  (testing "numeric API strings are parsed before KPI math"
    (is (= 11000
           (ev-bonus/bonus-total [{:bonus_amount "6000.00"}
                                  {:bonus_amount "5000.00"}]))))

  (testing "invalid or missing numbers do not poison the total"
    (is (= 6000
           (ev-bonus/bonus-total [{:bonus_amount "6000.00"}
                                  {:bonus_amount nil}
                                  {:bonus_amount "abc"}])))))

(deftest average-achievement-test
  (testing "achievement average accepts the serialized backend shape"
    (is (= 0.75
           (ev-bonus/average-achievement [{:achievement_pct "1.0000"}
                                          {:achievement_pct "0.5000"}]))))

  (testing "empty data has no average"
    (is (nil? (ev-bonus/average-achievement [])))))

(deftest available-years-test
  (testing "year filter starts at the historical baseline and includes next year"
    (is (= [2024 2025 2026 2027]
           (vec (ev-bonus/available-years (js/Date. 2026 4 11)))))))

(deftest run-summary-message-test
  (testing "plain success message stays compact"
    (is (= "2 bônus EV recalculados"
           (ev-bonus/run-summary-message {:bonuses_computed 2
                                          :skipped_final 0
                                          :skipped_no_salary 0}))))

  (testing "skipped rows are visible to the admin"
    (is (= "3 bônus EV recalculados · 1 finais preservados · 2 sem salário base"
           (ev-bonus/run-summary-message {:bonuses_computed 3
                                          :skipped_final 1
                                          :skipped_no_salary 2})))))

(deftest run-log-lines-test
  (testing "zero work with no skips points to missing achievements"
    (is (= ["Nenhum bônus foi recalculado."
            "Não há atingimentos cadastrados para este trimestre. Gere ou edite Atingimento por EV antes de calcular o bônus."]
           (ev-bonus/run-log-lines {:bonuses_computed 0
                                    :skipped_final 0
                                    :skipped_no_salary 0}))))

  (testing "zero work due to salary setup shows the blocking reason"
    (is (= ["Nenhum bônus foi recalculado."
            "2 registros não rodaram por falta de salário base no cadastro do EV."]
           (ev-bonus/run-log-lines {:bonuses_computed 0
                                    :skipped_final 0
                                    :skipped_no_salary 2}))))

  (testing "computed and skipped entries are both visible"
    (is (= ["3 registros recalculados."
            "1 registros já estavam finais e foram preservados."
            "2 registros não rodaram por falta de salário base no cadastro do EV."]
           (ev-bonus/run-log-lines {:bonuses_computed 3
                                    :skipped_final 1
                                    :skipped_no_salary 2})))))
