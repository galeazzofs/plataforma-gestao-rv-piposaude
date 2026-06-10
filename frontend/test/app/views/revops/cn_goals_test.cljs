(ns app.views.revops.cn-goals-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.views.revops.cn-goals :as g]))

(deftest parse-sao-test
  (testing "aceita vírgula e ponto como decimal"
    (is (= 6.5 (g/parse-sao "6,5")))
    (is (= 6.5 (g/parse-sao "6.5")))
    (is (= 6 (g/parse-sao "6,")))
    (is (= 7 (g/parse-sao 7))))
  (testing "rejeita lixo, sinais e separador de milhar"
    (is (nil? (g/parse-sao "abc")))
    (is (nil? (g/parse-sao "6,5x")))
    (is (nil? (g/parse-sao "-3")))
    (is (nil? (g/parse-sao "1.234,56")))
    (is (nil? (g/parse-sao "")))
    (is (nil? (g/parse-sao nil)))))

(deftest sao-valid?-test
  (testing "vazio é válido (significa zerar a meta)"
    (is (g/sao-valid? ""))
    (is (g/sao-valid? nil))
    (is (g/sao-valid? "   ")))
  (testing "números válidos e inválidos"
    (is (g/sao-valid? "6,5"))
    (is (not (g/sao-valid? "x")))
    (is (not (g/sao-valid? "1,2,3")))))

(deftest fmt-sao-test
  ;; SAO é contagem, não dinheiro: sem casas decimais forçadas.
  (is (= "6" (g/fmt-sao "6.00")))
  (is (= "6,5" (g/fmt-sao "6.5")))
  (is (= "1.234,5" (g/fmt-sao 1234.5)))
  (is (nil? (g/fmt-sao "x"))))

(deftest num->input-test
  (is (= "6,5" (g/num->input 6.5)))
  (is (= "7" (g/num->input 7))))

(deftest period-helpers-test
  (testing "prev-period vira o ano em janeiro"
    (is (= {:month 12 :year 2025} (g/prev-period {:month 1 :year 2026})))
    (is (= {:month 5 :year 2026} (g/prev-period {:month 6 :year 2026}))))
  (testing "period-key e parse-period-key são inversos"
    (is (= {:month 6 :year 2026}
           (g/parse-period-key (g/period-key {:month 6 :year 2026})))))
  (testing "rótulos"
    (is (= "jun/2026" (g/period-label-short {:month 6 :year 2026})))
    (is (= "Junho 2026" (g/period-title {:month 6 :year 2026}))))
  (testing "current-period e year-options"
    (is (= {:month 6 :year 2026} (g/current-period (js/Date. 2026 5 10))))
    (is (= [2025 2026 2027] (g/year-options 2026)))))

(deftest coverage-state-test
  (is (= :full (g/coverage-state 5 5)))
  (is (= :part (g/coverage-state 2 5)))
  (is (nil? (g/coverage-state 0 5)))
  (is (nil? (g/coverage-state nil 5)))
  (is (nil? (g/coverage-state 2 0))))

(deftest input-display-test
  (let [row {:cn_id "a" :sao_target "6.50"}]
    (testing "sem edição mostra o salvo formatado"
      (is (= "6,5" (g/input-display row {}))))
    (testing "edição crua tem precedência, inclusive vazia"
      (is (= "9,9" (g/input-display row {"a" {:sao_target "9,9"}})))
      (is (= "" (g/input-display row {"a" {:sao_target ""}}))))))

(deftest totals-test
  (let [rows [{:cn_id "a" :porte "G+" :sao_target "6.00"}
              {:cn_id "b" :porte "M" :sao_target "1.00"}
              {:cn_id "c" :porte nil :sao_target "2.00"}]]
    (testing "sem edições usa os valores salvos; sem porte não soma vidas"
      (is (= {:sao 9 :vidas 12375}
             (g/totals rows {}))))
    (testing "edições sobrescrevem o salvo"
      (is (= {:sao 10.5 :vidas (+ 12000 937.5)}
             (g/totals rows {"b" {:sao_target "2,5"}
                             "c" {:sao_target "2"}}))))))

(deftest build-items-test
  (let [items (g/build-items {"a" {:sao_target "6,5"}
                              "b" {:sao_target ""}})]
    (testing "normaliza decimal para ponto; vazio vira 0"
      (is (= #{{:cn_id "a" :sao_target "6.5"}
               {:cn_id "b" :sao_target "0"}}
             (set items))))))

(deftest merge-prev-edits-test
  (let [rows [{:cn_id "a" :sao_target nil}
              {:cn_id "b" :sao_target "0.00"}
              {:cn_id "c" :sao_target "5.00"}
              {:cn_id "d" :sao_target nil}]
        prev [{:cn_id "a" :sao_target "7.00"}
              {:cn_id "b" :sao_target "4.00"}
              {:cn_id "c" :sao_target "9.00"}
              {:cn_id "d" :sao_target "8.00"}]
        {:keys [edits applied]}
        (g/merge-prev-edits rows prev {"d" {:sao_target "3"}})]
    (testing "preenche apenas linhas zeradas sem edição"
      (is (= 2 applied))
      (is (= "7" (get-in edits ["a" :sao_target])))
      (is (= "4" (get-in edits ["b" :sao_target]))))
    (testing "não toca meta salva positiva nem edição existente"
      (is (nil? (get edits "c")))
      (is (= "3" (get-in edits ["d" :sao_target]))))
    (testing "mês anterior sem meta positiva não gera nada"
      (is (= 0 (:applied (g/merge-prev-edits
                          [{:cn_id "a" :sao_target nil}]
                          [{:cn_id "a" :sao_target "0.00"}]
                          nil)))))))
