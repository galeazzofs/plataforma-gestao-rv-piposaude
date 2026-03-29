(ns app.ds.notifications
  (:require [app.ds.tokens :as t]
            [re-frame.core :as rf]
            [reagent.core :as r]))

(defn notification-item
  "Single notification row."
  [{:keys [title body read? created-at on-click]}]
  [:div {:style {:padding "12px 16px"
                 :border-bottom (str "1px solid " t/bg-subtle)
                 :cursor "pointer"
                 :background (if read? t/bg-card t/beige-100)
                 :transition t/transition-fast}
         :on-click on-click}
   [:div {:style {:display "flex" :justify-content "space-between" :align-items "flex-start" :gap "8px"}}
    [:div {:style {:flex "1"}}
     [:p {:style {:font-size (:sm t/font-sizes)
                  :font-weight (if read? (:regular t/font-weights) (:semibold t/font-weights))
                  :color t/text-primary
                  :margin "0 0 2px"}}
      title]
     (when body
       [:p {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :margin "0"}}
        body])]
    (when created-at
      [:span {:style {:font-size (:xs t/font-sizes) :color t/text-disabled :white-space "nowrap"}}
       created-at])]])

(defn notification-bell
  "Notification bell icon with unread count badge.
   Props: unread-count, on-click"
  [{:keys [unread-count on-click]}]
  [:button {:style {:position "relative"
                    :background "none"
                    :border "none"
                    :cursor "pointer"
                    :padding "8px"
                    :color t/text-secondary}
            :on-click on-click}
   [:span {:style {:font-size "20px"}} "🔔"]
   (when (and unread-count (> unread-count 0))
     [:span {:style {:position "absolute"
                     :top "2px"
                     :right "2px"
                     :background t/error-default
                     :color t/color-white
                     :font-size "10px"
                     :font-weight (:bold t/font-weights)
                     :border-radius (:full t/border-radius)
                     :min-width "18px"
                     :height "18px"
                     :display "flex"
                     :align-items "center"
                     :justify-content "center"
                     :padding "0 4px"}}
      (if (> unread-count 99) "99+" (str unread-count))])])

(defn notification-dropdown
  "Notification dropdown panel.
   Props: open?, notifications, on-close, on-mark-read-all"
  [{:keys [open? notifications on-close on-mark-read-all]}]
  (when open?
    [:div {:style {:position "absolute"
                   :top "100%"
                   :right "0"
                   :width "360px"
                   :background t/bg-card
                   :border (str "1px solid " t/border-default)
                   :border-radius (:lg t/border-radius)
                   :box-shadow (:lg t/shadows)
                   :z-index "1000"
                   :overflow "hidden"}}
     ;; Header
     [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"
                    :padding "16px" :border-bottom (str "1px solid " t/border-default)}}
      [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:semibold t/font-weights)}}
       "Notificações"]
      (when on-mark-read-all
        [:button {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :background "none" :border "none" :cursor "pointer"}
                  :on-click on-mark-read-all}
         "Marcar todas como lidas"])]
     ;; List
     [:div {:style {:max-height "400px" :overflow-y "auto"}}
      (if (empty? notifications)
        [:div {:style {:padding "32px 16px" :text-align "center" :color t/text-disabled :font-size (:sm t/font-sizes)}}
         "Sem notificações"]
        (for [n notifications]
          ^{:key (:id n)}
          [notification-item n]))]]))
