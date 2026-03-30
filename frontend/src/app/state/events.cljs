(ns app.state.events
  (:require [re-frame.core :as rf]
            [app.state.db :as db]))

(rf/reg-event-db
 :initialize-db
 (fn [_ _]
   db/initial-db))

;; UI events
(rf/reg-event-db
 :ui/show-toast
 (fn [db [_ {:keys [type message duration]}]]
   (assoc-in db [:ui :toast] {:type type :message message :duration (or duration 3000)})))

(rf/reg-event-db
 :ui/clear-toast
 (fn [db _]
   (assoc-in db [:ui :toast] nil)))

(rf/reg-event-db
 :ui/show-modal
 (fn [db [_ modal-id data]]
   (assoc-in db [:ui :active-modal] {:id modal-id :data data})))

(rf/reg-event-db
 :ui/close-modal
 (fn [db _]
   (assoc-in db [:ui :active-modal] nil)))

;; Navigation — wired to reitit via :navigate! effect (registered in routes.cljs)
;; Accepts a route-name keyword or a [route-name params] vector
(rf/reg-event-fx
 :navigate
 (fn [{:keys [db]} [_ route]]
   {:db db
    :navigate! route}))
