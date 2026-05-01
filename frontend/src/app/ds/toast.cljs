(ns app.ds.toast
  (:require [re-frame.core :as rf]
            [app.ds.tokens :as t]
            [app.ds.layout :as layout]))

;; Toast notifications — Pipo styling.

(defn- toast-icon-name [type]
  (case type
    :success "check"
    :error   "alert"
    :warning "alert"
    "info"))

(defn- toast-colors [type]
  (case type
    :success {:bg t/success-light    :color t/success-dark    :border t/success-default}
    :error   {:bg t/error-light      :color t/error-dark      :border t/error-default}
    :warning {:bg t/warning-light    :color t/warning-dark    :border t/warning-default}
    {:bg t/bg-card :color t/text-primary :border t/border-default}))

(defn toast
  "Single toast. Props: type (:success :error :warning :info), message, on-close"
  [{:keys [type message on-close]}]
  (let [{:keys [bg color border]} (toast-colors type)]
    [:div {:style {:display "flex" :align-items "center" :gap "12px"
                   :padding "12px 14px"
                   :background bg :color color
                   :border (str "1px solid " border)
                   :border-radius (:sm t/border-radius)
                   :box-shadow (:lg t/shadows)
                   :min-width "320px" :max-width "480px"
                   :font-family t/font-ui :font-size "13px" :font-weight "500"}}
     [:div {:style {:width "20px" :height "20px" :flex-shrink 0
                    :display "inline-flex" :align-items "center" :justify-content "center"}}
      [layout/icon (toast-icon-name type) {:width 16 :height 16}]]
     [:span {:style {:flex 1}} message]
     [:button {:on-click on-close
               :style {:background "none" :border "none" :cursor "pointer"
                       :color color :padding "0 4px" :font-size "14px"
                       :font-family t/font-mono}}
      "✕"]]))

(defn toast-container
  "Container for toast notifications, reads :ui/toast from re-frame db."
  []
  (let [toast-data @(rf/subscribe [:ui/toast])]
    (when toast-data
      [:div {:style {:position "fixed" :bottom "24px" :right "24px" :z-index 2000}}
       [toast {:type (:type toast-data)
               :message (:message toast-data)
               :on-close #(rf/dispatch [:ui/clear-toast])}]])))
