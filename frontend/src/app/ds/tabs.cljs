(ns app.ds.tabs
  (:require [app.ds.tokens :as t]
            [reagent.core :as r]))

(defn tab-group
  "Tab navigation group.
   tabs: [{:key :overview :label \"Visão Geral\"} ...]
   active: currently active tab key
   on-change: fn called with tab key on click"
  [{:keys [tabs active on-change]}]
  [:div {:style {:display "flex"
                 :border-bottom (str "1px solid " t/border-default)
                 :gap "0"}}
   (for [{:keys [key label]} tabs]
     ^{:key key}
     [:button {:style {:padding "10px 20px"
                       :font-size (:sm t/font-sizes)
                       :font-weight (if (= key active) (:semibold t/font-weights) (:regular t/font-weights))
                       :color (if (= key active) t/color-primary t/text-secondary)
                       :background "none"
                       :border "none"
                       :border-bottom (if (= key active) (str "2px solid " t/color-primary) "2px solid transparent")
                       :cursor "pointer"
                       :transition t/transition-fast
                       :margin-bottom "-1px"}
               :on-click #(when on-change (on-change key))}
      label])])

(defn tab
  "Individual tab panel — renders children only when active."
  [{:keys [active? class]} & children]
  (when active?
    (into [:div {:class class}] children)))
