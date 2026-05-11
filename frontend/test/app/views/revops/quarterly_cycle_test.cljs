(ns app.views.revops.quarterly-cycle-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.views.revops.quarterly-cycle :as qc]))

(deftest suggest-cycle-test
  (testing "empty cycle list suggests the current quarter"
    (is (= {:quarter 2 :year 2026}
           (qc/suggest-cycle [] nil (js/Date. 2026 4 11)))))

  (testing "locked latest cycle suggests the next quarter"
    (is (= {:quarter 1 :year 2027}
           (qc/suggest-cycle [{:quarter 4 :year 2026 :status "LOCKED"}]
                             {:quarter 4 :year 2026 :status "LOCKED"}
                             (js/Date. 2026 4 11)))))

  (testing "open latest cycle does not suggest another cycle"
    (is (nil? (qc/suggest-cycle [{:quarter 2 :year 2026 :status "OPEN"}]
                                {:quarter 2 :year 2026 :status "OPEN"}
                                (js/Date. 2026 4 11))))))
