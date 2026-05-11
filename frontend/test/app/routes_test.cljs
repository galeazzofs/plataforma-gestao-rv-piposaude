(ns app.routes-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.routes :as routes]))

(deftest route-allowed?-test
  (testing "public routes (no :role) are open to everyone"
    (is (routes/route-allowed? nil "EV"))
    (is (routes/route-allowed? nil "CN"))
    (is (routes/route-allowed? nil nil)))

  (testing "role-gated routes only let listed roles in"
    (is (routes/route-allowed? #{:EV :ADMIN} "EV"))
    (is (routes/route-allowed? #{:EV :ADMIN} "ADMIN"))
    (is (not (routes/route-allowed? #{:EV :ADMIN} "CN")))
    (is (not (routes/route-allowed? #{:CN :ADMIN} "EV")))
    (is (not (routes/route-allowed? #{:ADMIN} "FINANCE")))
    (is (not (routes/route-allowed? #{:LIDER_VENDAS :ADMIN} "EV"))))

  (testing "a missing user role is denied on role-gated routes"
    (is (not (routes/route-allowed? #{:EV :ADMIN} nil)))))

(defn- match [name & {:keys [role]}]
  {:data (cond-> {:name name} role (assoc :role role))})

(defn- db-with [role]
  {:auth (when role {:user {:role role}})})

(deftest handle-route-changed-commits-public-routes
  (testing "logged-out user — any route is committed without navigation"
    (let [fx (routes/handle-route-changed
              (db-with nil)
              (match :revops/users :role #{:ADMIN}))]
      (is (some? (:db fx)))
      (is (not (contains? fx :navigate!)))))

  (testing "logged-in user on a route they're allowed on — committed, no redirect"
    (let [fx (routes/handle-route-changed
              (db-with "EV")
              (match :ev/dashboard :role #{:EV :ADMIN}))]
      (is (some? (:db fx)))
      (is (not (contains? fx :navigate!))))))

(deftest handle-route-changed-redirects-home-and-login
  (testing "logged-in user hitting :home is bounced to their landing"
    (let [fx (routes/handle-route-changed
              (db-with "CN")
              (match :home))]
      (is (= :cn/dashboard (:navigate! fx)))))

  (testing "logged-in user hitting :login is bounced to their landing"
    (let [fx (routes/handle-route-changed
              (db-with "EV")
              (match :login))]
      (is (= :ev/dashboard (:navigate! fx))))))

(deftest handle-route-changed-blocks-unauthorized-routes
  (testing "EV trying /admin/users is redirected to ev dashboard, route NOT committed"
    (let [fx (routes/handle-route-changed
              (db-with "EV")
              (match :revops/users :role #{:ADMIN}))]
      (is (= :ev/dashboard (:navigate! fx)))
      ;; Critically: :db is NOT updated, so the view doesn't flash the
      ;; unauthorized page before the redirect lands.
      (is (not (contains? fx :db)))))

  (testing "CN trying /ev/dashboard is redirected to cn dashboard"
    (let [fx (routes/handle-route-changed
              (db-with "CN")
              (match :ev/dashboard :role #{:EV :ADMIN}))]
      (is (= :cn/dashboard (:navigate! fx)))
      (is (not (contains? fx :db)))))

  (testing "EV trying /cn/simulator is redirected to ev dashboard"
    (let [fx (routes/handle-route-changed
              (db-with "EV")
              (match :cn/simulator :role #{:CN :ADMIN}))]
      (is (= :ev/dashboard (:navigate! fx)))
      (is (not (contains? fx :db))))))
