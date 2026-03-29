(ns app.core
  (:require [reagent.dom :as rdom]
            [re-frame.core :as rf]))

(defn app-root []
  [:div {:style {:display "flex"
                 :justify-content "center"
                 :align-items "center"
                 :height "100vh"
                 :font-family "'Inter', sans-serif"}}
   [:h1 "Plataforma de Comissões"]])

(defn ^:export init! []
  (rf/dispatch-sync [:initialize-db])
  (rdom/render [app-root]
               (.getElementById js/document "app")))
