(ns app.ds.notifications
  (:require [app.ds.tokens :as t]
            [app.ds.layout :as layout]))

;; Notifications — Pipo styling: bell with red dot, dropdown panel.

(defn notification-item
  "Single notification row."
  [{:keys [title body read? created-at on-click]}]
  [:div {:on-click on-click
         :style {:padding "12px 16px"
                 :border-bottom (str "1px solid " t/border-default)
                 :cursor "pointer"
                 :background (if read? t/bg-card t/beige-100)
                 :transition (str "background " t/transition-fast)}}
   [:div {:style {:display "flex" :justify-content "space-between" :align-items "flex-start" :gap "8px"}}
    [:div {:style {:flex 1}}
     [:p {:style {:font-family t/font-ui :font-size "13px"
                  :font-weight (if read? "500" "600")
                  :color t/text-primary :margin "0 0 2px"}}
      title]
     (when body
       [:p {:style {:font-size "12px" :color t/text-tertiary :margin 0}}
        body])]
    (when created-at
      [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-disabled :white-space "nowrap"}}
       created-at])]])

(defn notification-bell
  "Bell icon with unread count badge.
   Props: unread-count, on-click"
  [{:keys [unread-count on-click]}]
  [:button.icon-btn {:on-click on-click :aria-label "Notificações"}
   [layout/icon "bell" {:width 16 :height 16}]
   (when (and unread-count (> unread-count 0))
     [:span {:style {:position "absolute" :top "4px" :right "4px"
                     :background t/error-default :color t/color-white
                     :font-family t/font-mono :font-size "9px" :font-weight "700"
                     :border-radius "9999px"
                     :min-width "16px" :height "16px"
                     :display "flex" :align-items "center" :justify-content "center"
                     :padding "0 4px"
                     :border (str "1.5px solid " t/bg-card)}}
      (if (> unread-count 99) "99+" (str unread-count))])])

(defn notification-dropdown
  "Notification dropdown panel.
   Props: open?, notifications, on-close, on-mark-read-all"
  [{:keys [open? notifications on-close on-mark-read-all]}]
  (when open?
    [:div {:style {:position "absolute" :top "100%" :right 0
                   :width "380px"
                   :background t/bg-card
                   :border (str "1px solid " t/border-default)
                   :border-radius (:md t/border-radius)
                   :box-shadow (:lg t/shadows)
                   :z-index 1000 :overflow "hidden"
                   :margin-top "8px"}}
     [:div {:style {:display "flex" :justify-content "space-between" :align-items "center"
                    :padding "16px 20px" :border-bottom (str "1px solid " t/border-default)}}
      [:strong {:style {:font-family t/font-heading :font-size "14px" :font-weight "600"
                        :color t/text-primary}}
       "Notificações"]
      (when on-mark-read-all
        [:button {:on-click on-mark-read-all
                  :style {:font-family t/font-mono :font-size "11px"
                          :color t/text-tertiary :background "none" :border "none"
                          :cursor "pointer"}}
         "marcar todas como lidas"])]
     [:div {:style {:max-height "420px" :overflow-y "auto"}}
      (if (empty? notifications)
        [:div {:style {:padding "32px 16px" :text-align "center"
                       :color t/text-disabled :font-size "13px"}}
         "Sem notificações"]
        (for [n notifications]
          ^{:key (:id n)}
          [notification-item n]))]]))
