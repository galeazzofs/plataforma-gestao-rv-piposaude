(ns app.views.revops.events-test
  (:require [cljs.test :refer-macros [deftest is testing]]
            [app.api.endpoints :as ep]
            [app.views.revops.events :as events]))

(deftest fetch-users-defaults-to-active-users
  (testing "the Users tab should hide soft-deleted users after removal"
    (let [fx (events/fetch-users-fx {})]
      (is (= ep/users (get-in fx [:http :url])))
      (is (= true (get-in fx [:db :admin :users-loading?]))))))
