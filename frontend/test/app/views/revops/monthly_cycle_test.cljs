(ns app.views.revops.monthly-cycle-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.views.revops.monthly-cycle :as mc]))

(deftest suggest-cycle-test
  (testing "empty cycle list suggests the current month"
    (is (= {:month 5 :year 2026}
           (mc/suggest-cycle [] nil (js/Date. 2026 4 11)))))

  (testing "locked latest cycle suggests the next month"
    (is (= {:month 6 :year 2026}
           (mc/suggest-cycle [{:month 5 :year 2026 :status "LOCKED"}]
                             {:month 5 :year 2026 :status "LOCKED"}
                             (js/Date. 2026 4 11)))))

  (testing "locked December rolls over to January of the next year"
    (is (= {:month 1 :year 2027}
           (mc/suggest-cycle [{:month 12 :year 2026 :status "LOCKED"}]
                             {:month 12 :year 2026 :status "LOCKED"}
                             (js/Date. 2026 11 20)))))

  (testing "open latest cycle does not suggest another cycle"
    (is (nil? (mc/suggest-cycle [{:month 5 :year 2026 :status "OPEN"}]
                                {:month 5 :year 2026 :status "OPEN"}
                                (js/Date. 2026 4 11))))))

(deftest components-for-test
  (testing "mid-quarter months carry only the two apurações"
    (is (= ["ev_apuracao" "cn_apuracao"]
           (mapv first (mc/components-for {:month 5 :is_quarter_end false})))))

  (testing "quarter-end months append the three bonuses, in sequence"
    (is (= ["ev_apuracao" "cn_apuracao" "cn_bonus" "ev_bonus" "leadership_bonus"]
           (mapv first (mc/components-for {:month 6 :is_quarter_end true}))))))

(deftest component-of-test
  (testing "reads keyword and string keys from the payload"
    (is (= {:status "DRAFT"}
           (mc/component-of {:components {:ev_apuracao {:status "DRAFT"}}}
                            "ev_apuracao")))
    (is (= {:status "DRAFT"}
           (mc/component-of {:components {"ev_apuracao" {:status "DRAFT"}}}
                            "ev_apuracao")))))

(deftest current-step-key-test
  (let [cycle {:month 6 :is_quarter_end true
               :components {:ev_apuracao {:status "LOCKED"}
                            :cn_apuracao {:status "VALIDATING"}
                            :cn_bonus    {:status "PENDING"}
                            :ev_bonus    {:status "PENDING"}
                            :leadership_bonus {:status "PENDING"}}}]
    (testing "first non-LOCKED component in sequence order"
      (is (= "cn_apuracao" (mc/current-step-key cycle))))
    (testing "fully locked cycle has no current step"
      (is (nil? (mc/current-step-key
                 {:month 5 :is_quarter_end false
                  :components {:ev_apuracao {:status "LOCKED"}
                               :cn_apuracao {:status "LOCKED"}}}))))))

(deftest progress-test
  (is (= {:done 1 :total 5}
         (mc/progress {:month 6 :is_quarter_end true
                       :components {:ev_apuracao {:status "LOCKED"}
                                    :cn_apuracao {:status "DRAFT"}
                                    :cn_bonus    {:status "PENDING"}
                                    :ev_bonus    {:status "PENDING"}
                                    :leadership_bonus {:status "PENDING"}}})))
  (is (= {:done 0 :total 2}
         (mc/progress {:month 5 :is_quarter_end false :components {}}))))

(deftest month-navigation-test
  (is (= {:month 4 :year 2026} (mc/prev-month {:month 5 :year 2026})))
  (is (= {:month 12 :year 2025} (mc/prev-month {:month 1 :year 2026})))
  (is (= {:month 6 :year 2026}
         (select-keys (mc/cycle-for-month [{:month 6 :year 2026 :id "x"}]
                                          {:month 6 :year 2026})
                      [:month :year])))
  (is (nil? (mc/cycle-for-month [{:month 5 :year 2026}] {:month 6 :year 2026}))))

(deftest next-action-test
  (let [cycle {:id "cy1" :month 6 :year 2026 :quarter 2 :is_quarter_end true}]
    (testing "EV apuração PENDING → create"
      (let [a (mc/next-action "ev_apuracao" {:status "PENDING"} cycle)]
        (is (= :request (:kind a)))
        (is (= "/appraisals" (:url a)))
        (is (= {:month 6 :year 2026} (:body a)))))
    (testing "EV apuração DRAFT → run calc via transition"
      (let [a (mc/next-action "ev_apuracao"
                              {:status "DRAFT" :appraisal_id "ap1"} cycle)]
        (is (= "/appraisals/ap1/transition" (:url a)))
        (is (= {:to "CALCULATING"} (:body a)))))
    (testing "EV apuração VALIDATING → no admin action (EVs validate)"
      (is (nil? (mc/next-action "ev_apuracao"
                                {:status "VALIDATING" :appraisal_id "ap1"}
                                cycle))))
    (testing "EV apuração REVOPS_REVIEW → lock with confirm"
      (let [a (mc/next-action "ev_apuracao"
                              {:status "REVOPS_REVIEW" :appraisal_id "ap1"}
                              cycle)]
        (is (= {:to "LOCKED"} (:body a)))
        (is (true? (:confirm? a)))))
    (testing "CN apuração PENDING → navigate to the detail page (inputs live there)"
      (let [a (mc/next-action "cn_apuracao" {:status "PENDING"} cycle)]
        (is (= :navigate (:kind a)))
        (is (= :revops/cn-appraisal (:route a)))))
    (testing "CN apuração CALCULATING → bulk transition to VALIDATING"
      (let [a (mc/next-action "cn_apuracao" {:status "CALCULATING"} cycle)]
        (is (= "/commissions/cn/appraisal/transition-month" (:url a)))
        (is (= {:month 6 :year 2026 :to "VALIDATING"} (:body a)))))
    (testing "CN apuração REVOPS_REVIEW → bulk finalize"
      (let [a (mc/next-action "cn_apuracao" {:status "REVOPS_REVIEW"} cycle)]
        (is (= "/commissions/cn/appraisal/finalize-month" (:url a)))
        (is (= {:month 6 :year 2026} (:body a)))
        (is (true? (:confirm? a)))))
    (testing "Bônus CN PENDING → run; CALCULATING → finalize"
      (is (= "/commissions/cn/quarterly-bonus"
             (:url (mc/next-action "cn_bonus" {:status "PENDING"} cycle))))
      (is (= "/commissions/cn/quarterly-bonus/finalize"
             (:url (mc/next-action "cn_bonus" {:status "CALCULATING"} cycle)))))
    (testing "Bônus EV PENDING → run; CALCULATING → finalize"
      (is (= {:quarter 2 :year 2026}
             (:body (mc/next-action "ev_bonus" {:status "PENDING"} cycle))))
      (is (= "/commissions/ev/bonus/finalize"
             (:url (mc/next-action "ev_bonus" {:status "CALCULATING"} cycle)))))
    (testing "Liderança PENDING → navigate (inputs live there)"
      (is (= :navigate
             (:kind (mc/next-action "leadership_bonus" {:status "PENDING"} cycle)))))
    (testing "Liderança transitions need the row id"
      (is (nil? (mc/next-action "leadership_bonus"
                                {:status "LIDER_REVIEW" :appraisal_id nil}
                                cycle)))
      (is (= "/commissions/leadership/appraisal/ld1/transition"
             (:url (mc/next-action "leadership_bonus"
                                   {:status "LIDER_REVIEW" :appraisal_id "ld1"}
                                   cycle)))))
    (testing "LOCKED components have no action"
      (is (nil? (mc/next-action "ev_apuracao" {:status "LOCKED"} cycle)))
      (is (nil? (mc/next-action "cn_bonus" {:status "LOCKED"} cycle))))))
