(ns app.views.revops.appraisal-review-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.views.revops.appraisal-review :as ar]))

(deftest signoff-status-test
  (testing "nil quando o EV não tem bloco de signoff (apuração antiga)"
    (is (nil? (ar/signoff-status {}))))
  (testing "done / changed / pending"
    (is (= :done (ar/signoff-status {:signoff {:status "DONE"}})))
    (is (= :changed (ar/signoff-status
                     {:signoff {:status "PENDING" :values_changed true}})))
    (is (= :pending (ar/signoff-status
                     {:signoff {:status "PENDING" :values_changed false}})))))

(deftest signoff-progress-test
  (is (= {:total 3 :done 1 :all-done? false}
         (ar/signoff-progress
          {:signoff_totals {:total 3 :done 1 :all_done false}})))
  (is (= {:total 0 :done 0 :all-done? false}
         (ar/signoff-progress {}))))

(deftest conference-active?-test
  (testing "ativa só em CALCULATING com totais presentes"
    (is (ar/conference-active?
         {:status "CALCULATING" :signoff_totals {:total 2 :done 0}}))
    (is (not (ar/conference-active?
              {:status "VALIDATING" :signoff_totals {:total 2 :done 2}})))
    (is (not (ar/conference-active? {:status "CALCULATING"})))))

(deftest sort-evs-for-conference-test
  (testing "pendentes (incl. valores-mudaram) primeiro, alfabético dentro"
    (is (= ["Bia" "Caio" "Ana"]
           (map :ev_name
                (ar/sort-evs-for-conference
                 [{:ev_name "Ana" :signoff {:status "DONE"}}
                  {:ev_name "Caio" :signoff {:status "PENDING"
                                             :values_changed true}}
                  {:ev_name "Bia" :signoff {:status "PENDING"}}]))))))

(deftest filter-evs-by-signoff-test
  (let [evs [{:ev_name "Ana" :signoff {:status "DONE"}}
             {:ev_name "Bia" :signoff {:status "PENDING"}}]]
    (is (= ["Bia"] (map :ev_name (ar/filter-evs-by-signoff evs :pendentes))))
    (is (= ["Ana"] (map :ev_name (ar/filter-evs-by-signoff evs :conferidos))))
    (is (= ["Ana" "Bia"] (map :ev_name (ar/filter-evs-by-signoff evs :todos))))))

(deftest release-blocked?-test
  (testing "bloqueia em CALCULATING com pendências"
    (is (ar/release-blocked?
         {:status "CALCULATING" :signoff_totals {:total 3 :done 1}})))
  (testing "libera com 100% ou fora do CALCULATING ou sem dados"
    (is (not (ar/release-blocked?
              {:status "CALCULATING" :signoff_totals {:total 3 :done 3}})))
    (is (not (ar/release-blocked?
              {:status "REVOPS_REVIEW" :signoff_totals {:total 3 :done 1}})))
    (is (not (ar/release-blocked? {:status "CALCULATING"})))))
