(ns app.ds.inputs
  (:require [app.ds.tokens :as t]
            [app.ds.typography :as typo]))

(defn input
  "Text input.
   Props: value, on-change, placeholder, type, error, disabled, label, required."
  [{:keys [value on-change placeholder type error disabled label required name]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
   (when label
     [typo/label {:required required} label])
   [:input {:style {:font-family t/font-family
                    :font-size (:sm t/font-sizes)
                    :padding "8px 12px"
                    :height "40px"
                    :border (str "1px solid " (if error t/error-default t/border-default))
                    :border-radius (:md t/border-radius)
                    :background (if disabled t/bg-subtle t/bg-card)
                    :color (if disabled t/text-disabled t/text-primary)
                    :outline "none"
                    :transition t/transition-fast
                    :width "100%"}
            :type (or type "text")
            :value value
            :name name
            :placeholder placeholder
            :disabled disabled
            :on-change #(when on-change (on-change (.. % -target -value)))}]
   (when error
     [:span {:style {:font-size (:xs t/font-sizes) :color t/error-default}} error])])

(defn select
  "Select dropdown.
   options: [{:value \"x\" :label \"X\"} ...]"
  [{:keys [value on-change options label required disabled error]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "4px"}}
   (when label
     [typo/label {:required required} label])
   [:select {:style {:font-family t/font-family
                     :font-size (:sm t/font-sizes)
                     :padding "8px 12px"
                     :height "40px"
                     :border (str "1px solid " (if error t/error-default t/border-default))
                     :border-radius (:md t/border-radius)
                     :background t/bg-card
                     :color t/text-primary
                     :width "100%"
                     :cursor "pointer"}
             :value (or value "")
             :disabled disabled
             :on-change #(when on-change (on-change (.. % -target -value)))}
    (for [{:keys [value label]} options]
      ^{:key value}
      [:option {:value value} label])]])

(defn file-upload
  "File upload input for XLSX.
   Props: on-file, accept, label."
  [{:keys [on-file accept label]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
   (when label
     [typo/label {} label])
   [:label {:style {:display "flex"
                    :align-items "center"
                    :justify-content "center"
                    :padding "24px"
                    :border (str "2px dashed " t/border-default)
                    :border-radius (:lg t/border-radius)
                    :background t/bg-subtle
                    :cursor "pointer"
                    :transition t/transition-fast
                    :text-align "center"}}
    [:input {:type "file"
             :accept (or accept ".xlsx,.xls")
             :style {:display "none"}
             :on-change #(when on-file
                           (let [file (-> % .-target .-files (aget 0))]
                             (when file (on-file file))))}]
    [:div {:style {:display "flex" :flex-direction "column" :gap "4px" :align-items "center"}}
     [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}} "Clique ou arraste o arquivo aqui"]
     [:span {:style {:font-size (:xs t/font-sizes) :color t/text-disabled}} "Formatos: .xlsx, .xls"]]]])
