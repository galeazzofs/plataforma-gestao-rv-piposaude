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
