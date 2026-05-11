(ns app.ds.nav-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.ds.nav :as nav]
            [app.routes :as routes]))

(defn- route-keys [items]
  (->> items (keep :route) set))

(deftest cn-and-ev-have-separate-nav
  (testing "CN nav exposes the CN dashboard, not the EV dashboard"
    (let [cn-routes (route-keys (nav/items-for-role "CN"))]
      (is (contains? cn-routes :cn/dashboard))
      (is (contains? cn-routes :cn/simulator))
      (is (not (contains? cn-routes :ev/dashboard)))
      (is (not (contains? cn-routes :ev/history)))
      (is (not (contains? cn-routes :ev/validation)))))

  (testing "EV nav does not include CN-only screens"
    (let [ev-routes (route-keys (nav/items-for-role "EV"))]
      (is (contains? ev-routes :ev/dashboard))
      (is (contains? ev-routes :ev/history))
      (is (contains? ev-routes :ev/validation))
      (is (not (contains? ev-routes :cn/simulator)))
      (is (not (contains? ev-routes :cn/dashboard))))))

(deftest role-landing-points-to-own-dashboard
  (testing "Each role lands on the dashboard built for it"
    (is (= :revops/dashboard       (routes/role->landing "ADMIN")))
    (is (= :finance/dashboard      (routes/role->landing "FINANCE")))
    (is (= :lider-vendas/dashboard (routes/role->landing "LIDER_VENDAS")))
    (is (= :ev/dashboard           (routes/role->landing "EV")))
    (is (= :cn/dashboard           (routes/role->landing "CN")))
    (is (= :no-role                (routes/role->landing "UNKNOWN")))))
