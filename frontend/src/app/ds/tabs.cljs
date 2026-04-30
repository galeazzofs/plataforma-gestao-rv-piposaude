(ns app.ds.tabs
  (:require [app.ds.tokens :as t]))

(defn tab-group
  "Tab navigation group, styled to match the design's .tabs spec.
   tabs: [{:key :overview :label \"Visão Geral\"} ...]
   active: currently active tab key
   on-change: fn called with tab key on click"
  [{:keys [tabs active on-change]}]
  [:div {:style {:display "flex" :gap "2px"
                 :border-bottom (str "1px solid " t/border-default)
                 :margin-bottom "-1px"}}
   (for [{:keys [key label]} tabs]
     ^{:key key}
     [:button {:style {:padding "10px 14px"
                       :font-family t/font-ui
                       :font-weight (:semibold t/font-weights)
                       :font-size "13px"
                       :color (if (= key active) t/text-primary t/text-tertiary)
                       :background "none"
                       :border "none"
                       :border-bottom (if (= key active)
                                        (str "2px solid " t/color-primary)
                                        "2px solid transparent")
                       :cursor "pointer"
                       :transition (str "color " t/transition-fast ", border-color " t/transition-fast)}
               :on-click #(when on-change (on-change key))}
      label])])

(defn tab
  "Individual tab panel — renders children only when active."
  [{:keys [active? class]} & children]
  (when active?
    (into [:div {:class class}] children)))
